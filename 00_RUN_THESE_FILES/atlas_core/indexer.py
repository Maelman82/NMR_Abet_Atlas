from __future__ import annotations

import json
import os
import shutil
import sqlite3
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from .common import (
    best_datetime, classify_schedule, fast_file_fingerprint, json_dumps,
    norm_text, source_project_hint, write_csv,
)
from .database import AtlasError, ensure_cached_sqlite, event_count, get_events, get_sessions
from .metadata import animal_metadata_summary, load_metadata_csv, load_reconciliation_decisions
from .trials import reconstruct_trials, trial_dict

Progress = Optional[Callable[[str], None]]

SESSION_FIELDS = [
    "Source_Database", "Source_Path", "Database_Fingerprint", "Cached_SQLite", "Project_Hint",
    "SID", "Animal_ID", "Session_DateTime", "Schedule_Run_Date", "Schedule_Start_Time",
    "Schedule_Name", "Machine", "Task_Hint", "Session_Type_Hint", "Event_Count",
    "Reconstructed_Trials", "Has_Trial_Data", "SFinal", "SRecCount", "Schedule_Notes_JSON", "Parse_Status",
]

TRIAL_FIELDS = [
    "Source_Database", "Database_Fingerprint", "Project_Hint", "SID", "Animal_ID", "Session_DateTime",
    "Schedule_Name", "trial_index", "trial_counter", "stimulus_onset", "outcome_time", "outcome",
    "stimulus_duration_s", "current_image", "correct_image", "current_iti_s", "correct_grid_position",
    "hit", "miss", "false_alarm", "correct_rejection", "correction_trial_correct_rejection",
    "correction_trial_mistake", "response_latency_s", "reward_retrieval_latency_s",
]

SESSION_REPORT_FIELDS = SESSION_FIELDS + [
    "Atlas_Original_Animal_ID", "Atlas_Original_Project_Hint", "Reconciliation_Decision",
    "Reconciliation_Notes", "Cohort", "Sex", "Genotype", "Treatment",
]

TRIAL_REPORT_FIELDS = TRIAL_FIELDS + [
    "Atlas_Original_Animal_ID", "Atlas_Original_Project_Hint", "Reconciliation_Decision",
    "Reconciliation_Notes",
]


def _decision_key(project: str, animal: str) -> tuple[str, str]:
    return (norm_text(project).lower(), norm_text(animal).lower())


def _build_decision_maps(decisions: list[dict[str, str]]) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, dict[str, str]], list[dict[str, Any]]]:
    by_project: dict[tuple[str, str], dict[str, str]] = {}
    by_animal: dict[str, dict[str, str]] = {}
    problems: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, str]] = {}

    for d in decisions:
        animal = norm_text(d.get("Atlas_DB_Animal_ID"))
        project = norm_text(d.get("Atlas_Project_Hint"))
        if not animal:
            continue
        key = _decision_key(project, animal)
        if key in seen:
            problems.append({"Status": "RECONCILIATION_DUPLICATE_DECISION", "Project": project, "Animal_ID": animal, "Detail": "Duplicate row in decision file; last row was used"})
        seen[key] = d
        if project:
            by_project[key] = d
        else:
            by_animal[animal.lower()] = d
    return by_project, by_animal, problems


def _find_decision(row: dict[str, Any], by_project: dict[tuple[str, str], dict[str, str]], by_animal: dict[str, dict[str, str]]) -> dict[str, str] | None:
    project = norm_text(row.get("Project_Hint") or row.get("project_hint"))
    animal = norm_text(row.get("Animal_ID") or row.get("animal_id"))
    return by_project.get(_decision_key(project, animal)) or by_animal.get(animal.lower())


def _apply_decision_to_session(row: dict[str, Any], decision: dict[str, str] | None) -> dict[str, Any] | None:
    out = dict(row)
    out["Atlas_Original_Animal_ID"] = row.get("Animal_ID", "")
    out["Atlas_Original_Project_Hint"] = row.get("Project_Hint", "")
    out["Reconciliation_Decision"] = ""
    out["Reconciliation_Notes"] = ""
    if not decision:
        return out

    action = norm_text(decision.get("Decision")).upper()
    out["Reconciliation_Decision"] = action or "BLANK"
    out["Reconciliation_Notes"] = decision.get("Reviewer_Notes", "")
    if action in {"", "UNSURE", "EXCLUDE"}:
        return None

    final_project = decision.get("Final_Project_Group") or row.get("Project_Hint", "")
    final_animal = decision.get("Correct_Animal_ID") if action == "REMAP" else ""
    out["Project_Hint"] = final_project
    out["Animal_ID"] = final_animal or row.get("Animal_ID", "")
    out["Cohort"] = decision.get("Final_Cohort", "")
    out["Sex"] = decision.get("Final_Sex", "")
    out["Genotype"] = decision.get("Final_Genotype", "")
    out["Treatment"] = decision.get("Final_Treatment", "")
    return out


def _apply_decision_to_trial(row: dict[str, Any], decision: dict[str, str] | None) -> dict[str, Any] | None:
    out = dict(row)
    out["Atlas_Original_Animal_ID"] = row.get("Animal_ID", "")
    out["Atlas_Original_Project_Hint"] = row.get("Project_Hint", "")
    out["Reconciliation_Decision"] = ""
    out["Reconciliation_Notes"] = ""
    if not decision:
        return out

    action = norm_text(decision.get("Decision")).upper()
    out["Reconciliation_Decision"] = action or "BLANK"
    out["Reconciliation_Notes"] = decision.get("Reviewer_Notes", "")
    if action in {"", "UNSURE", "EXCLUDE"}:
        return None

    out["Project_Hint"] = decision.get("Final_Project_Group") or row.get("Project_Hint", "")
    if action == "REMAP" and decision.get("Correct_Animal_ID"):
        out["Animal_ID"] = decision["Correct_Animal_ID"]
    return out


def _init_index_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS databases (
        fingerprint TEXT PRIMARY KEY, source_database TEXT, source_path TEXT, cached_sqlite TEXT,
        file_size INTEGER, file_mtime_ns INTEGER, status TEXT, error TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions (
        session_uid TEXT PRIMARY KEY, source_database TEXT, source_path TEXT, database_fingerprint TEXT,
        cached_sqlite TEXT, project_hint TEXT, sid TEXT, animal_id TEXT, session_datetime TEXT,
        schedule_run_date TEXT, schedule_start_time TEXT, schedule_name TEXT, machine TEXT,
        task_hint TEXT, session_type_hint TEXT, event_count INTEGER, reconstructed_trials INTEGER,
        has_trial_data INTEGER, sfinal TEXT, sreccount TEXT, schedule_notes_json TEXT, parse_status TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_animal ON sessions(animal_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_datetime ON sessions(session_datetime);
    CREATE INDEX IF NOT EXISTS idx_sessions_project_animal ON sessions(project_hint, animal_id);
    CREATE TABLE IF NOT EXISTS trials (
        trial_uid TEXT PRIMARY KEY, session_uid TEXT, source_database TEXT, database_fingerprint TEXT,
        project_hint TEXT, sid TEXT, animal_id TEXT, session_datetime TEXT, schedule_name TEXT,
        trial_index INTEGER, trial_counter REAL, stimulus_onset REAL, outcome_time REAL, outcome TEXT,
        stimulus_duration_s REAL, current_image REAL, correct_image REAL, current_iti_s REAL,
        correct_grid_position REAL, hit INTEGER, miss INTEGER, false_alarm INTEGER, correct_rejection INTEGER,
        correction_trial_correct_rejection INTEGER, correction_trial_mistake INTEGER,
        response_latency_s REAL, reward_retrieval_latency_s REAL
    );
    CREATE INDEX IF NOT EXISTS idx_trials_session ON trials(session_uid);
    CREATE INDEX IF NOT EXISTS idx_trials_animal ON trials(animal_id);
    CREATE TABLE IF NOT EXISTS metadata_rows (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT, project_group TEXT, cohort TEXT, timepoint_label TEXT,
        sex TEXT, genotype TEXT, treatment TEXT, strain TEXT, animal_id TEXT, raw_json TEXT
    );
    """)
    return conn


def _process_database(source: Path, cache_db_dir: Path, force: bool = False) -> dict[str, Any]:
    fp = fast_file_fingerprint(source)
    cached = cache_db_dir / f"{source.stem}__{fp}.sqlite"
    result: dict[str, Any] = {
        "fingerprint": fp, "source": str(source), "source_database": source.name,
        "cached": str(cached), "sessions": [], "trials": [], "status": "OK", "error": "",
    }
    try:
        ensure_cached_sqlite(source, cached, force=force)
        conn = sqlite3.connect(f"file:{cached.resolve()}?mode=ro", uri=True)
        try:
            sessions = get_sessions(conn)
            project = source_project_hint(source.name)
            for sid, meta in sessions.items():
                schedule = norm_text(meta.get("Schedule"))
                task_hint, session_type = classify_schedule(schedule)
                events = get_events(conn, sid)
                trials = reconstruct_trials(events)
                session_dt = best_datetime(meta.get("Schedule_Start_Time"), meta.get("SRunDate"))
                notes = {k: v for k, v in meta.items() if k not in {"SID","Schedule","Machine","SRunDate","SFinal","SRecCount","Animal_ID","Schedule_Start_Time"}}
                session_uid = f"{fp}:{sid}"
                srow = {
                    "session_uid": session_uid,
                    "Source_Database": source.name, "Source_Path": str(source), "Database_Fingerprint": fp,
                    "Cached_SQLite": str(cached), "Project_Hint": project, "SID": sid,
                    "Animal_ID": norm_text(meta.get("Animal_ID")), "Session_DateTime": session_dt,
                    "Schedule_Run_Date": norm_text(meta.get("SRunDate")),
                    "Schedule_Start_Time": norm_text(meta.get("Schedule_Start_Time")),
                    "Schedule_Name": schedule, "Machine": norm_text(meta.get("Machine")),
                    "Task_Hint": task_hint, "Session_Type_Hint": session_type,
                    "Event_Count": len(events), "Reconstructed_Trials": len(trials),
                    "Has_Trial_Data": int(bool(trials)), "SFinal": norm_text(meta.get("SFinal")),
                    "SRecCount": norm_text(meta.get("SRecCount")), "Schedule_Notes_JSON": json_dumps(notes),
                    "Parse_Status": "OK",
                }
                result["sessions"].append(srow)
                for t in trials:
                    td = trial_dict(t)
                    result["trials"].append({
                        "trial_uid": f"{session_uid}:{td['trial_index']}", "session_uid": session_uid,
                        "Source_Database": source.name, "Database_Fingerprint": fp, "Project_Hint": project,
                        "SID": sid, "Animal_ID": srow["Animal_ID"], "Session_DateTime": session_dt,
                        "Schedule_Name": schedule, **td,
                    })
        finally:
            conn.close()
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    return result


def _insert_result(conn: sqlite3.Connection, result: dict[str, Any], source: Path) -> None:
    fp = result["fingerprint"]
    st = source.stat()
    conn.execute(
        "INSERT OR REPLACE INTO databases VALUES (?,?,?,?,?,?,?,?)",
        (fp, source.name, str(source), result["cached"], st.st_size, st.st_mtime_ns, result["status"], result["error"]),
    )
    # Fingerprints change when a DB changes, so remove older copies of the same source path.
    old_fps = [r[0] for r in conn.execute("SELECT fingerprint FROM databases WHERE source_path=? AND fingerprint<>?", (str(source), fp)).fetchall()]
    for old in old_fps:
        conn.execute("DELETE FROM sessions WHERE database_fingerprint=?", (old,))
        conn.execute("DELETE FROM trials WHERE database_fingerprint=?", (old,))
        conn.execute("DELETE FROM databases WHERE fingerprint=?", (old,))

    if result["status"] != "OK":
        return
    for s in result["sessions"]:
        conn.execute("""INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            s["session_uid"], s["Source_Database"], s["Source_Path"], s["Database_Fingerprint"], s["Cached_SQLite"],
            s["Project_Hint"], str(s["SID"]), s["Animal_ID"], s["Session_DateTime"], s["Schedule_Run_Date"],
            s["Schedule_Start_Time"], s["Schedule_Name"], s["Machine"], s["Task_Hint"], s["Session_Type_Hint"],
            int(s["Event_Count"]), int(s["Reconstructed_Trials"]), int(s["Has_Trial_Data"]), s["SFinal"], s["SRecCount"],
            s["Schedule_Notes_JSON"], s["Parse_Status"],
        ))
    for t in result["trials"]:
        conn.execute("""INSERT OR REPLACE INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            t["trial_uid"], t["session_uid"], t["Source_Database"], t["Database_Fingerprint"], t["Project_Hint"],
            str(t["SID"]), t["Animal_ID"], t["Session_DateTime"], t["Schedule_Name"], t["trial_index"],
            t["trial_counter"], t["stimulus_onset"], t["outcome_time"], t["outcome"], t["stimulus_duration_s"],
            t["current_image"], t["correct_image"], t["current_iti_s"], t["correct_grid_position"], t["hit"], t["miss"],
            t["false_alarm"], t["correct_rejection"], t["correction_trial_correct_rejection"], t["correction_trial_mistake"],
            t["response_latency_s"], t["reward_retrieval_latency_s"],
        ))


def _query_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    old = conn.row_factory; conn.row_factory = sqlite3.Row
    try: return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally: conn.row_factory = old


def _load_metadata_into_index(conn: sqlite3.Connection, metadata_path: Path | None) -> list[dict[str, str]]:
    conn.execute("DELETE FROM metadata_rows")
    rows = load_metadata_csv(metadata_path)
    for r in rows:
        conn.execute(
            "INSERT INTO metadata_rows(project_group,cohort,timepoint_label,sex,genotype,treatment,strain,animal_id,raw_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (r.get("Project_Group",""), r.get("Cohort",""), r.get("Timepoint_Label",""), r.get("Sex",""),
             r.get("Genotype",""), r.get("Treatment",""), r.get("Strain",""), r.get("AnimalID",""), json_dumps(r)),
        )
    return rows


def _export_reports(conn: sqlite3.Connection, output_dir: Path, metadata_rows: list[dict[str, str]], export_trials_csv: bool,
                    reconciliation_decisions: list[dict[str, str]] | None = None) -> dict[str, Path]:
    reports = output_dir / "reports"; reports.mkdir(parents=True, exist_ok=True)
    raw_sessions = _query_dicts(conn, """
      SELECT source_database AS Source_Database, source_path AS Source_Path, database_fingerprint AS Database_Fingerprint,
             cached_sqlite AS Cached_SQLite, project_hint AS Project_Hint, sid AS SID, animal_id AS Animal_ID,
             session_datetime AS Session_DateTime, schedule_run_date AS Schedule_Run_Date,
             schedule_start_time AS Schedule_Start_Time, schedule_name AS Schedule_Name, machine AS Machine,
             task_hint AS Task_Hint, session_type_hint AS Session_Type_Hint, event_count AS Event_Count,
             reconstructed_trials AS Reconstructed_Trials, has_trial_data AS Has_Trial_Data, sfinal AS SFinal,
             sreccount AS SRecCount, schedule_notes_json AS Schedule_Notes_JSON, parse_status AS Parse_Status
      FROM sessions ORDER BY animal_id, session_datetime, source_database, CAST(sid AS INTEGER)
    """)
    decisions = reconciliation_decisions or []
    decision_by_project, decision_by_animal, decision_problems = _build_decision_maps(decisions)
    sessions: list[dict[str, Any]] = []
    excluded_by_decision: list[dict[str, Any]] = []
    for s in raw_sessions:
        decision = _find_decision(s, decision_by_project, decision_by_animal)
        clean = _apply_decision_to_session(s, decision)
        if clean is None:
            excluded_by_decision.append({
                "Status": "RECONCILIATION_EXCLUDED_OR_UNRESOLVED",
                "Project": s.get("Project_Hint", ""),
                "Animal_ID": s.get("Animal_ID", ""),
                "Detail": f"Decision={decision.get('Decision','BLANK') if decision else 'BLANK'}; {s.get('Source_Database','')} SID={s.get('SID','')}",
            })
        else:
            sessions.append(clean)

    raw_session_path = reports / "ATLAS_SESSION_MASTER_RAW_UNFILTERED.csv"
    write_csv(raw_session_path, raw_sessions, SESSION_FIELDS)
    session_path = reports / "ATLAS_SESSION_MASTER.csv"
    write_csv(session_path, sessions, SESSION_REPORT_FIELDS)

    db_rows = _query_dicts(conn, "SELECT source_database AS Source_Database, source_path AS Source_Path, fingerprint AS Database_Fingerprint, cached_sqlite AS Cached_SQLite, file_size AS File_Size_Bytes, status AS Parse_Status, error AS Error FROM databases ORDER BY source_database")
    db_path = reports / "ATLAS_DATABASE_INVENTORY.csv"
    write_csv(db_path, db_rows, ["Source_Database","Source_Path","Database_Fingerprint","Cached_SQLite","File_Size_Bytes","Parse_Status","Error"])

    decision_meta_rows: list[dict[str, str]] = []
    for d in decisions:
        action = norm_text(d.get("Decision")).upper()
        if action not in {"KEEP", "REMAP"}:
            continue
        animal = d.get("Correct_Animal_ID") if action == "REMAP" and d.get("Correct_Animal_ID") else d.get("Atlas_DB_Animal_ID", "")
        if not animal:
            continue
        decision_meta_rows.append({
            "Project_Group": d.get("Final_Project_Group") or d.get("Atlas_Project_Hint", ""),
            "AnimalID": animal,
            "Cohort": d.get("Final_Cohort", ""),
            "Sex": d.get("Final_Sex", ""),
            "Genotype": d.get("Final_Genotype", ""),
            "Treatment": d.get("Final_Treatment", ""),
            "Strain": "",
            "Timepoint_Label": "",
        })
    meta_summary = animal_metadata_summary(metadata_rows + decision_meta_rows)
    meta_path = reports / "ATLAS_ANIMAL_METADATA.csv"
    meta_fields = ["Project_Group","AnimalID","Cohort","Sex","Genotype","Treatment","Strain","Timepoints_In_Metadata","Metadata_Status","Metadata_Conflict_Fields"]
    write_csv(meta_path, meta_summary, meta_fields)

    # Lookup metadata by (project, animal), and by animal when globally unique.
    exact = {(m["Project_Group"], m["AnimalID"]): m for m in meta_summary}
    by_animal: dict[str, list[dict[str, str]]] = defaultdict(list)
    for m in meta_summary: by_animal[m["AnimalID"]].append(m)

    session_groups: dict[tuple[str,str], list[dict[str,Any]]] = defaultdict(list)
    for s in sessions:
        if s.get("Animal_ID"):
            session_groups[(s.get("Project_Hint", ""), s["Animal_ID"])].append(s)

    coverage: list[dict[str, Any]] = []
    found_keys = set()
    for (project, animal), ss in sorted(session_groups.items()):
        found_keys.add((project, animal))
        dbs = sorted({s["Source_Database"] for s in ss})
        dts = [s["Session_DateTime"] for s in ss if s["Session_DateTime"]]
        type_counts = Counter(s["Session_Type_Hint"] for s in ss)
        task_counts = Counter(s["Task_Hint"] for s in ss)
        m = exact.get((project, animal))
        match_status = "FOUND_IN_DB_AND_METADATA" if m else ""
        if not m:
            candidates = by_animal.get(animal, [])
            if len(candidates) == 1:
                m = candidates[0]; match_status = "FOUND_IN_DB_AND_METADATA_PROJECT_INFERRED"
            elif len(candidates) > 1:
                match_status = "FOUND_IN_DB_METADATA_AMBIGUOUS_PROJECT"
            else:
                match_status = "FOUND_IN_DB_NOT_METADATA"
        coverage.append({
            "Project_Hint": project, "Animal_ID": animal, "Metadata_Match_Status": match_status,
            "Metadata_Project": m.get("Project_Group", "") if m else "", "Cohort": m.get("Cohort", "") if m else "",
            "Sex": m.get("Sex", "") if m else "", "Genotype": m.get("Genotype", "") if m else "",
            "Treatment": m.get("Treatment", "") if m else "", "Total_Sessions": len(ss), "Databases_Count": len(dbs),
            "Databases": " | ".join(dbs), "First_Session": min(dts) if dts else "", "Last_Session": max(dts) if dts else "",
            "Sessions_With_Trial_Data": sum(int(s["Has_Trial_Data"] or 0) for s in ss),
            "Habituation": type_counts.get("Habituation",0), "Pretraining": type_counts.get("Pretraining",0),
            "Stage_1": type_counts.get("Stage 1",0), "Stage_2": type_counts.get("Stage 2",0),
            "Stage_3": type_counts.get("Stage 3",0), "Stage_4": type_counts.get("Stage 4",0),
            "Probe_2b": type_counts.get("Probe 2b",0), "Other_Unclassified": type_counts.get("Other/Unclassified",0),
            "CPT_Sessions": task_counts.get("CPT",0), "5CSRTT_Sessions": task_counts.get("5CSRTT",0),
            "PVD_Sessions": task_counts.get("PVD",0), "TUNL_Sessions": task_counts.get("TUNL",0), "LD_Sessions": task_counts.get("LD",0),
        })
    cov_fields = ["Project_Hint","Animal_ID","Metadata_Match_Status","Metadata_Project","Cohort","Sex","Genotype","Treatment","Total_Sessions","Databases_Count","Databases","First_Session","Last_Session","Sessions_With_Trial_Data","Habituation","Pretraining","Stage_1","Stage_2","Stage_3","Stage_4","Probe_2b","Other_Unclassified","CPT_Sessions","5CSRTT_Sessions","PVD_Sessions","TUNL_Sessions","LD_Sessions"]
    cov_path = reports / "ATLAS_ANIMAL_COVERAGE.csv"; write_csv(cov_path, coverage, cov_fields)

    reconciliation: list[dict[str, Any]] = []
    reconciliation.extend(decision_problems)
    reconciliation.extend(excluded_by_decision)
    for d in decisions:
        action = norm_text(d.get("Decision")).upper()
        if action in {"", "UNSURE"}:
            reconciliation.append({
                "Status": "RECONCILIATION_NEEDS_REVIEW",
                "Project": d.get("Atlas_Project_Hint", ""),
                "Animal_ID": d.get("Atlas_DB_Animal_ID", ""),
                "Detail": "Decision file row is blank or UNSURE; matching sessions/trials are excluded from clean reports until reviewed",
            })
    for c in coverage:
        if c["Metadata_Match_Status"] != "FOUND_IN_DB_AND_METADATA":
            reconciliation.append({"Status": c["Metadata_Match_Status"], "Project": c["Project_Hint"], "Animal_ID": c["Animal_ID"], "Detail": f"{c['Total_Sessions']} sessions found"})
    for m in meta_summary:
        project, animal = m["Project_Group"], m["AnimalID"]
        # Exact project match preferred; if DB had no project hint, a unique animal can still count.
        exact_found = (project, animal) in found_keys
        inferred_found = any(a == animal for p,a in found_keys) and len(by_animal.get(animal,[])) == 1
        if not (exact_found or inferred_found):
            reconciliation.append({"Status":"METADATA_NOT_FOUND_IN_DATABASES","Project":project,"Animal_ID":animal,"Detail":"No indexed session matched this metadata animal/project"})
        if m.get("Metadata_Status") == "CONFLICT":
            reconciliation.append({"Status":"METADATA_CONFLICT","Project":project,"Animal_ID":animal,"Detail":m.get("Metadata_Conflict_Fields","")})

    # Duplicate candidate: same animal, normalized datetime and schedule in >1 source DB.
    dup_groups: dict[tuple[str,str,str], list[dict[str,Any]]] = defaultdict(list)
    for s in sessions:
        if s["Animal_ID"] and s["Session_DateTime"]:
            dup_groups[(s["Animal_ID"], s["Session_DateTime"], s["Schedule_Name"])].append(s)
    for key, vals in dup_groups.items():
        if len(vals) > 1:
            reconciliation.append({"Status":"POSSIBLE_DUPLICATE_SESSION","Project":"","Animal_ID":key[0],"Detail":" | ".join(f"{v['Source_Database']} SID={v['SID']}" for v in vals)})

    qc_path = reports / "ATLAS_QC_RECONCILIATION.csv"; write_csv(qc_path, reconciliation, ["Status","Project","Animal_ID","Detail"])

    trial_path = reports / "ATLAS_TRIAL_MASTER.csv"
    raw_trial_path = reports / "ATLAS_TRIAL_MASTER_RAW_UNFILTERED.csv"
    if export_trials_csv:
        raw_trials = _query_dicts(conn, "SELECT source_database AS Source_Database, database_fingerprint AS Database_Fingerprint, project_hint AS Project_Hint, sid AS SID, animal_id AS Animal_ID, session_datetime AS Session_DateTime, schedule_name AS Schedule_Name, trial_index, trial_counter, stimulus_onset, outcome_time, outcome, stimulus_duration_s, current_image, correct_image, current_iti_s, correct_grid_position, hit, miss, false_alarm, correct_rejection, correction_trial_correct_rejection, correction_trial_mistake, response_latency_s, reward_retrieval_latency_s FROM trials ORDER BY animal_id, session_datetime, trial_index")
        clean_trials: list[dict[str, Any]] = []
        for t in raw_trials:
            decision = _find_decision(t, decision_by_project, decision_by_animal)
            clean = _apply_decision_to_trial(t, decision)
            if clean is not None:
                clean_trials.append(clean)
        write_csv(raw_trial_path, raw_trials, TRIAL_FIELDS)
        write_csv(trial_path, clean_trials, TRIAL_REPORT_FIELDS)
    return {"session_master":session_path,"session_master_raw":raw_session_path,"database_inventory":db_path,"animal_metadata":meta_path,"animal_coverage":cov_path,"qc":qc_path,"trial_master":trial_path if export_trials_csv else Path(""),"trial_master_raw":raw_trial_path if export_trials_csv else Path("")}


def build_atlas(input_dir: Path, output_dir: Path, metadata_path: Path | None = None, workers: int = 6,
                force_rebuild: bool = False, export_trials_csv: bool = False, progress: Progress = None,
                reconciliation_path: Path | None = None) -> dict[str, Any]:
    input_dir = input_dir.expanduser().resolve(); output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_db_dir = output_dir / "cache" / "databases"; cache_db_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "cache" / "NMR_ABET_Atlas.sqlite"; index_path.parent.mkdir(parents=True, exist_ok=True)

    dbs = sorted([p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in {".abetdb",".mdb",".db",".sqlite",".sqlite3"}])
    if not dbs: raise AtlasError(f"No ABET/SQLite database files found in {input_dir}")
    workers = max(1, min(int(workers), len(dbs), 12))
    if progress: progress(f"Found {len(dbs)} databases. Using {workers} workers.")

    conn = _init_index_db(index_path)
    try:
        metadata_rows = _load_metadata_into_index(conn, metadata_path)
        reconciliation_decisions = load_reconciliation_decisions(reconciliation_path)
        if progress and reconciliation_path:
            progress(f"Loaded {len(reconciliation_decisions)} reconciliation decision row(s) from {reconciliation_path.name}.")
        conn.commit()

        existing = {r[0] for r in conn.execute("SELECT fingerprint FROM databases WHERE status='OK'").fetchall()}
        jobs: list[Path] = []
        reused = 0
        for db in dbs:
            fp = fast_file_fingerprint(db)
            if not force_rebuild and fp in existing:
                reused += 1
                if progress: progress(f"CACHE HIT: {db.name}")
            else:
                jobs.append(db)
        if progress and reused: progress(f"Reusing {reused} unchanged database cache(s).")

        if jobs:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {pool.submit(_process_database, db, cache_db_dir, force_rebuild): db for db in jobs}
                done = 0
                for fut in as_completed(future_map):
                    db = future_map[fut]; done += 1
                    try: result = fut.result()
                    except Exception as exc:
                        result = {"fingerprint":fast_file_fingerprint(db),"source":str(db),"source_database":db.name,"cached":"","sessions":[],"trials":[],"status":"ERROR","error":f"{type(exc).__name__}: {exc}"}
                    _insert_result(conn, result, db); conn.commit()
                    if progress: progress(f"[{done}/{len(jobs)}] {db.name}: {result['status']} — {len(result.get('sessions',[]))} sessions, {len(result.get('trials',[]))} reconstructed trials")

        # Remove index rows for source files no longer selected/present in this input folder.
        selected_paths = {str(p) for p in dbs}
        indexed_paths = [r[0] for r in conn.execute("SELECT source_path FROM databases").fetchall()]
        for p in indexed_paths:
            if p not in selected_paths:
                fps = [r[0] for r in conn.execute("SELECT fingerprint FROM databases WHERE source_path=?", (p,)).fetchall()]
                for fp in fps:
                    conn.execute("DELETE FROM sessions WHERE database_fingerprint=?", (fp,)); conn.execute("DELETE FROM trials WHERE database_fingerprint=?", (fp,)); conn.execute("DELETE FROM databases WHERE fingerprint=?", (fp,))
        conn.commit()

        outputs = _export_reports(conn, output_dir, metadata_rows, export_trials_csv, reconciliation_decisions)
        counts = {
            "databases": conn.execute("SELECT COUNT(*) FROM databases WHERE status='OK'").fetchone()[0],
            "database_errors": conn.execute("SELECT COUNT(*) FROM databases WHERE status<>'OK'").fetchone()[0],
            "sessions": conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            "animals": conn.execute("SELECT COUNT(DISTINCT animal_id) FROM sessions WHERE animal_id<>''").fetchone()[0],
            "trials": conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0],
        }
        if progress: progress(f"Atlas complete: {counts['databases']} DBs, {counts['animals']} animal IDs, {counts['sessions']} sessions, {counts['trials']} reconstructed CPT-like trials.")
        return {"index": index_path, "outputs": outputs, "counts": counts}
    finally:
        conn.close()
