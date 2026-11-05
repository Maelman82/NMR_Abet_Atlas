#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, math, sqlite3, statistics, sys, traceback
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

NORMAL = NormalDist()


# Exact legacy Taylor/Lecanemab 49-column project schema.
# Spelling, punctuation, capitalization and order are intentionally preserved.
TAYLOR_49_COLUMNS = [
    "AnimalID", "Age", "Sex", "Treatment", "Genotype", "Strain", "ExpName", "Housing",
    "LightCycle", "PISiteUser", "SessionName", "Image", "Image_Description", "sessionInfoName",
    "Intervention", "S_ID",
    "AVG_Average - Correct Choice Latency at 0.2s SD",
    "AVG_Average - Correct Choice Latency at 0.5s SD",
    "AVG_Average - Correct Choice Latency at 1s SD",
    "AVG_Average - Correct Choice Latency at 2s SD",
    "AVG_Average - Mistake Latency at 0.2s SD",
    "AVG_Average - Mistake Latency at 0.5s SD",
    "AVG_Average - Mistake Latency at 1s SD",
    "AVG_Average - Mistake Latency at 2s SD",
    "AVG_Average - Reward Retrieval Latency at 0.2s SD",
    "AVG_Average - Reward Retrieval Latency at 0.5s SD",
    "AVG_Average - Reward Retrieval Latency at 1s SD",
    "AVG_Average - Reward Retrieval Latency at 2s SD",
    "AVG_count at 0.2s", "AVG_count at 0.5s", "AVG_count at 1s", "AVG_count at 2s",
    "AVG_End Summary - CorrectRejection at 0.2s SD",
    "AVG_End Summary - CorrectRejection at 0.5s SD",
    "AVG_End Summary - CorrectRejection at 1s SD",
    "AVG_End Summary - CorrectRejection at 2s SD",
    "AVG_End Summary - Hits",
    "AVG_End Summary - Hits at 0.2s SD",
    "AVG_End Summary - Hits at 0.5s SD",
    "AVG_End Summary - Hits at 1s SD",
    "AVG_End Summary - Hits at 2s SD",
    "AVG_End Summary - Miss at 0.2s SD",
    "AVG_End Summary - Miss at 0.5s SD",
    "AVG_End Summary - Miss at 1s SD",
    "AVG_End Summary - Miss at 2s SD",
    "AVG_End Summary - Mistake at 0.2s SD",
    "AVG_End Summary - Mistake at 0.5s SD",
    "AVG_End Summary - Mistake at 1s SD",
    "AVG_End Summary - Mistake at 2s SD",
]
TAYLOR_DURATIONS = [(0.2,"0.2s"),(0.5,"0.5s"),(1.0,"1s"),(2.0,"2s")]


# Exact legacy 67-column extended CPT layout: Taylor 49 columns + Date_Time +
# chronological day + four SDT metrics for each of the four Probe 2b durations.
SDT_67_COLUMNS = []
for _label in ["0.2s", "0.5s", "1s", "2s"]:
    SDT_67_COLUMNS.extend([
        f"Hit Rate at {_label} SD",
        f"False Alarm Rate at {_label} SD",
        f"dPrime at {_label} SD",
        f"c Response Bias at {_label} SD",
    ])
LEGACY_67_COLUMNS = TAYLOR_49_COLUMNS + ["Date_Time", "chronological day"] + SDT_67_COLUMNS
LEGACY_67_BY_ITI_COLUMNS = (
    TAYLOR_49_COLUMNS + ["Date_Time", "chronological day", "Current_ITI_s"] + SDT_67_COLUMNS
)

LEGACY_TEXT_COLUMNS = {
    "AnimalID", "Sex", "Treatment", "Genotype", "Strain", "ExpName", "Housing",
    "LightCycle", "PISiteUser", "SessionName", "Image", "Image_Description",
    "sessionInfoName", "Intervention", "S_ID", "Date_Time",
}
LEGACY_NUMERIC_COLUMNS = (
    set(TAYLOR_49_COLUMNS)
    .union({"chronological day", "Current_ITI_s"})
    .union(SDT_67_COLUMNS)
    - LEGACY_TEXT_COLUMNS
)

# ----------------------------- helpers -----------------------------
def txt(x: Any) -> str:
    return "" if x is None else str(x).strip()

def num(x: Any):
    try:
        if x is None or x == "": return None
        return float(x)
    except Exception:
        return None

def normalize_legacy_numeric_cells(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    """Keep legacy CPT metric/count columns numeric for Excel and downstream tools."""
    numeric_fields = set(fields).intersection(LEGACY_NUMERIC_COLUMNS)
    if not numeric_fields:
        return rows
    out = []
    for row in rows:
        rr = row.copy()
        for field in numeric_fields:
            value = rr.get(field)
            if value is None or value == "":
                continue
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned.startswith("'"):
                    cleaned = cleaned[1:].strip()
                parsed = num(cleaned)
                if parsed is None:
                    continue
                value = parsed
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            rr[field] = value
        out.append(rr)
    return out

def parse_dt(s: Any):
    s=txt(s)
    if not s: return None
    for f in (None, "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%m/%d/%y %H:%M:%S"):
        try:
            return datetime.fromisoformat(s) if f is None else datetime.strptime(s,f)
        except Exception: pass
    return None

def parse_excel_or_text_dt(value: Any):
    """Parse Atlas ISO dates, text dates, or Excel serial dates."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(value))
        except Exception:
            return None
    value_txt = txt(value)
    if not value_txt:
        return None
    x = num(value_txt)
    if x is not None and 20000 < x < 80000:
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(x))
        except Exception:
            pass
    return parse_dt(value_txt)

def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))

def read_table(path: Path) -> list[dict[str, Any]]:
    """Read a CSV/XLSX session-selection table."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv(path)
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError(
                "openpyxl is required to read an Excel session-selection file. "
                "Run Install_or_Update_Python_Packages.bat, then run the extractor again."
            ) from exc
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb[wb.sheetnames[0]]
        row_iter = ws.iter_rows(values_only=True)
        try:
            headers = [txt(v) for v in next(row_iter)]
        except StopIteration:
            return []
        rows = []
        for values in row_iter:
            row = {headers[i]: values[i] for i in range(min(len(headers), len(values))) if headers[i]}
            if any(txt(v) for v in row.values()):
                rows.append(row)
        return rows
    raise ValueError(f"Unsupported session-selection file type: {path.suffix}. Use CSV or XLSX.")

def write_csv(path: Path, rows: list[dict[str,Any]], fields: list[str] | None=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields=[]
        seen=set()
        for r in rows:
            for k in r:
                if k not in seen: seen.add(k); fields.append(k)
    clean_rows = []
    for row in rows:
        rr = row.copy()
        for field in fields:
            value = rr.get(field)
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned.startswith("'") and num(cleaned[1:].strip()) is not None:
                    parsed = num(cleaned[1:].strip())
                    rr[field] = int(parsed) if isinstance(parsed, float) and parsed.is_integer() else parsed
        clean_rows.append(rr)
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader(); w.writerows(clean_rows)

def write_probe_session_selection_review_workbook(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write an Excel file where the reviewer marks exactly four Probe 2b sessions as USE."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required to create PROBE2B_SESSION_SELECTION_REVIEW.xlsx. "
            "Run Install_or_Update_Python_Packages.bat, then run the extractor again."
        ) from exc

    headers = [
        "Selected", "Project", "AnimalID", "Timepoint_Months", "Selection_Order",
        "Session_DateTime", "SID", "Source_Database", "Atlas_Master_SID",
        "Atlas_Master_Database_Fingerprint", "Atlas_Master_Session_DateTime",
        "Atlas_Master_Source_Database", "Review_Reason", "Reviewer_Notes",
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "Probe2b Session Choices"
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    if ws.max_row >= 2:
        dv = DataValidation(type="list", formula1='"USE,EXCLUDE,EXTRA,UNSURE"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"A2:A{ws.max_row}")

    for idx in range(1, ws.max_column + 1):
        letter = get_column_letter(idx)
        max_len = max(len(str(c.value or "")) for c in ws[letter])
        ws.column_dimensions[letter].width = max(12, min(max_len + 2, 45))

    how = wb.create_sheet("How To Use")
    how.append(["Step", "What to do"])
    how.append([1, "For each Project + AnimalID + Timepoint_Months block, mark exactly four sessions as USE."])
    how.append([2, "If the review reason says Timepoint_Months is wrong, edit Timepoint_Months to the correct age block before rerunning."])
    how.append([3, "If the review reason says Unassigned timepoint block, either set Timepoint_Months to 6/9/12 and mark the four real sessions USE, or mark the block EXCLUDE/EXTRA if it is not part of the planned design."])
    how.append([4, "Mark bad/problem sessions as EXCLUDE and true extras as EXTRA. Blank and UNSURE are ignored on rerun."])
    how.append([5, "Save this workbook, then rerun the extractor and choose this file as the Session selection CSV/XLSX."])
    how.append([6, "The extractor will use only the USE rows and renumber them as Probe_Session_Number 1-4."])
    for cell in how[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
    for idx in range(1, how.max_column + 1):
        letter = get_column_letter(idx)
        max_len = max(len(str(c.value or "")) for c in how[letter])
        how.column_dimensions[letter].width = max(12, min(max_len + 2, 80))

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)

def write_review_workbook(
    path: Path,
    animal_rows: list[dict[str, Any]],
    session_rows: list[dict[str, Any]],
    metadata_path: Path | None,
    selection_path: Path | None,
) -> None:
    """Write the rerunnable Excel review file for unknown animals/sessions.

    This workbook is intentionally compatible with read_decision_workbook():
    the Decisions sheet can be renamed/copied to ATLAS_RECONCILIATION_DECISIONS.xlsx
    or left beside the Atlas reports if this exact filename is used.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required to create the iterative Excel review workbook. "
            "Run Install_or_Update_Python_Packages.bat, then run the extractor again."
        ) from exc

    def add_rows(ws, headers, rows):
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for idx in range(1, ws.max_column + 1):
            letter = get_column_letter(idx)
            max_len = max(len(str(c.value or "")) for c in ws[letter])
            ws.column_dimensions[letter].width = max(12, min(max_len + 2, 50))

    def add_validation(ws, col_letter: str, formula: str):
        if ws.max_row < 2:
            return
        dv = DataValidation(type="list", formula1=f'"{formula}"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col_letter}2:{col_letter}{ws.max_row}")

    wb = Workbook()
    wb.remove(wb.active)
    how = wb.create_sheet("How To Use")
    add_rows(how, ["Step", "What to do", "What happens on rerun"], [
        {"Step": 1, "What to do": "Review blank or UNSURE rows in Decisions.", "What happens on rerun": "KEEP includes the animal, EXCLUDE removes it, REMAP changes the animal ID first."},
        {"Step": 2, "What to do": "Fill Final_Project_Group, Final_Cohort, Final_Sex, Final_Genotype, and Final_Treatment for kept/remapped animals.", "What happens on rerun": "These fields become the metadata used by the extractor."},
        {"Step": 3, "What to do": "Review Template Session Review if you supplied a session-selection/template file.", "What happens on rerun": "Rows with missing Atlas matches remain outside extraction until the template row can be matched or corrected."},
        {"Step": 4, "What to do": "Save as ATLAS_RECONCILIATION_DECISIONS.xlsx beside the Atlas reports, then rerun the extractor.", "What happens on rerun": "The extractor applies your decisions before making clean outputs."},
    ])

    decision_headers = [
        "Atlas_DB_Animal_ID", "Atlas_Project_Hint", "Decision", "Correct_Animal_ID",
        "Final_Project_Group", "Final_Cohort", "Final_Sex", "Final_Genotype",
        "Final_Treatment", "Reviewer_Notes", "Review_Category", "Suggested_Action",
        "Total_Sessions", "Probe_2b", "First_Session", "Last_Session",
        "Metadata_Match_Status", "Source_Metadata_File", "Source_Template_File",
    ]
    add_rows(wb.create_sheet("Decisions"), decision_headers, animal_rows)
    ws = wb["Decisions"]
    add_validation(ws, "C", "KEEP,EXCLUDE,REMAP,UNSURE")
    add_validation(ws, "E", "Lecanemab,Vaccine,Other,Unknown")
    add_validation(ws, "G", "Male,Female,Unknown")
    add_validation(ws, "H", "KI2TA-3,KI2TA-4,C57,AppKI,WT,Unknown")
    add_validation(ws, "I", "PBS,Lecanemab,Sham,Vaccine,Unknown")

    session_headers = [
        "Source_Row", "Decision", "Selection_Project", "Selection_Animal_ID",
        "Selection_Timepoint_Months", "Selection_Order", "Selection_DateTime_Parsed",
        "Selection_SID_Candidates", "Atlas_Master_Match", "Atlas_Master_Match_Count",
        "Atlas_Master_Match_Method", "Reviewer_Notes",
    ]
    add_rows(wb.create_sheet("Template Session Review"), session_headers, session_rows)
    add_validation(wb["Template Session Review"], "B", "KEEP,EXCLUDE,REMAP,UNSURE")

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)

def make_animal_review_rows(master_rows: list[dict[str, Any]], metadata_path: Path | None, selection_path: Path | None) -> list[dict[str, Any]]:
    by_key = defaultdict(list)
    for row in master_rows:
        project = txt(row.get("Project_Hint") or row.get("Project_Group") or row.get("Project"))
        animal = txt(row.get("Animal_ID") or row.get("AnimalID") or row.get("Animal ID"))
        if not animal:
            continue
        if txt(row.get("Metadata_Match_Status")) == "UNMATCHED" or not txt(row.get("Sex")) or not txt(row.get("Genotype")) or not txt(row.get("Treatment")):
            by_key[(project, animal)].append(row)
    review = []
    for (project, animal), rows in sorted(by_key.items()):
        dts = [parse_dt(r.get("Session_DateTime")) for r in rows if parse_dt(r.get("Session_DateTime"))]
        probe = sum(1 for r in rows if txt(r.get("Session_Type_Hint")).lower() == "probe 2b")
        total = len(rows)
        review.append({
            "Atlas_DB_Animal_ID": animal,
            "Atlas_Project_Hint": project,
            "Decision": "",
            "Correct_Animal_ID": "",
            "Final_Project_Group": project,
            "Final_Cohort": txt(rows[0].get("Cohort")),
            "Final_Sex": txt(rows[0].get("Sex")),
            "Final_Genotype": txt(rows[0].get("Genotype")),
            "Final_Treatment": txt(rows[0].get("Treatment")),
            "Reviewer_Notes": "",
            "Review_Category": "Needs metadata or keep/exclude decision",
            "Suggested_Action": "KEEP with final metadata, REMAP to corrected ID, or EXCLUDE",
            "Total_Sessions": total,
            "Probe_2b": probe,
            "First_Session": min(dts).isoformat(sep=" ") if dts else "",
            "Last_Session": max(dts).isoformat(sep=" ") if dts else "",
            "Metadata_Match_Status": txt(rows[0].get("Metadata_Match_Status")),
            "Source_Metadata_File": str(metadata_path) if metadata_path else "NOT FOUND",
            "Source_Template_File": str(selection_path) if selection_path else "",
        })
    return review

def percentile_linear(vals: list[float], p: float) -> float:
    s=sorted(vals); n=len(s)
    if n==1: return s[0]
    pos=(n-1)*p; lo=math.floor(pos); hi=math.ceil(pos)
    if lo==hi: return s[lo]
    return s[lo]+(s[hi]-s[lo])*(pos-lo)

def iqr_bounds(vals: list[float]):
    if len(vals)<4: return None,None
    q1=percentile_linear(vals,0.25); q3=percentile_linear(vals,0.75); i=q3-q1
    return q1-1.5*i, q3+1.5*i

def rate_metrics(h:int,m:int,fa:int,cr:int):
    ns=h+m; nn=fa+cr
    hr=h/ns if ns else None; far=fa/nn if nn else None
    out={"Hit_Rate":hr,"False_Alarm_Rate":far,"Hit_Rate_for_dprime":None,"False_Alarm_Rate_for_dprime":None,"d_prime":None,"criterion_c":None}
    if hr is None or far is None: return out
    hrc=(h-0.5)/ns if hr==1 else (h+0.5)/ns if hr==0 else hr
    farc=(fa-0.5)/nn if far==1 else (fa+0.5)/nn if far==0 else far
    out["Hit_Rate_for_dprime"]=hrc; out["False_Alarm_Rate_for_dprime"]=farc
    if 0<hrc<1 and 0<farc<1:
        zh=NORMAL.inv_cdf(hrc); zf=NORMAL.inv_cdf(farc)
        out["d_prime"]=zh-zf; out["criterion_c"]=-(zh+zf)/2
    return out

def mean(vals: Iterable[Any]):
    v=[float(x) for x in vals if x is not None and x!="" and not (isinstance(x,float) and math.isnan(x))]
    return sum(v)/len(v) if v else None

def cluster_sessions(rows: list[dict[str,Any]], max_gap_days: float=7.0):
    rows=sorted(rows,key=lambda r: parse_dt(r.get("Session_DateTime")) or datetime.min)
    clusters=[]; cur=[]; prev=None
    for r in rows:
        dt=parse_dt(r.get("Session_DateTime"))
        if prev is None or dt is None or (dt-prev).total_seconds()/86400 <= max_gap_days:
            cur.append(r)
        else:
            clusters.append(cur); cur=[r]
        prev=dt
    if cur: clusters.append(cur)
    return clusters

def session_key(r):
    return (txt(r.get("Database_Fingerprint")), txt(r.get("SID")))

def sid_text(value: Any) -> str:
    """Normalize Atlas/MouseBytes session IDs for exact whitelist matching."""
    value = txt(value)
    if value.endswith(".0"):
        value = value[:-2]
    return value

def project_text(row: dict[str, Any]) -> str:
    return txt(row.get("Project_Group") or row.get("Project_Hint") or row.get("Project"))

def animal_text(row: dict[str, Any]) -> str:
    return txt(row.get("AnimalID") or row.get("Animal_ID") or row.get("Animal ID"))

def selection_key(row: dict[str, Any]) -> tuple[str, str, str]:
    # The reviewed spreadsheet S_ID and Atlas master SID use different
    # numbering systems. The corrected whitelist therefore carries the Atlas
    # SID explicitly; fall back to the original field for legacy files.
    sid = row.get("Atlas_Master_SID") or (row.get("Source_SID") if "Source_SID" in row else row.get("SID"))
    fingerprint = row.get("Atlas_Master_Database_Fingerprint") or row.get("Database_Fingerprint")
    sid_token = f"{txt(fingerprint)}::{sid_text(sid)}" if txt(fingerprint) else sid_text(sid)
    return (project_text(row).casefold(), animal_text(row).casefold(), sid_token)

def selection_animal_text(row: dict[str, Any]) -> str:
    return txt(row.get("AnimalID") or row.get("Animal_ID") or row.get("Animal ID") or row.get("MouseID"))

def selection_project_text(row: dict[str, Any], default_project: str = "") -> str:
    return txt(row.get("Project") or row.get("Project_Group") or row.get("Project_Hint") or row.get("ExpName") or default_project)

def selection_timepoint(row: dict[str, Any]):
    for col in ["Timepoint_Months", "Timepoint", "Age", "AgeGroup", "Age_Group", "Month", "Months"]:
        x = num(row.get(col))
        if x is not None:
            xi = int(round(x))
            if xi in {6, 9, 12}:
                return xi
    return None

def row_source_timepoint(row: dict[str, Any]):
    # Prefer raw/source age columns over Timepoint_Months because the extractor
    # itself writes Timepoint_Months after chronological assignment.
    for col in ["Age", "AgeGroup", "Age_Group", "Timepoint", "Month", "Months", "Timepoint_Months"]:
        x = num(row.get(col))
        if x is not None:
            xi = int(round(x))
            if xi in {6, 9, 12}:
                return xi
    return None

def selection_order(row: dict[str, Any], fallback: int):
    for col in ["Selection_Order", "chronological day", "Chronological_Day", "Probe_Session_Number", "Session_Number"]:
        x = num(row.get(col))
        if x is not None:
            return int(round(x))
    return fallback

def is_selected_session(row: dict[str, Any]) -> bool:
    """Interpret session-selection review choices.

    Missing Selected means legacy source-of-truth rows are included. When the
    review workbook has a Selected column, only USE/YES-style rows are included.
    """
    if "Selected" not in row:
        return True
    return txt(row.get("Selected")).upper() in {"USE", "YES", "Y", "TRUE", "1"}

def selection_sid_candidates(row: dict[str, Any]) -> set[str]:
    cols = [
        "Atlas_Master_SID", "Source_SID", "SID", "S_ID", "sessionInfoName",
        "SessionInfoName", "Session_ID", "SessionID",
    ]
    return {sid_text(row.get(c)) for c in cols if sid_text(row.get(c))}

def selection_datetime(row: dict[str, Any]):
    for col in ["Session_DateTime", "Date_Time", "Schedule_Start_Time", "Schedule_Run_Date", "Date"]:
        dt = parse_excel_or_text_dt(row.get(col))
        if dt:
            return dt
    return None

def map_source_selection_to_atlas(
    selection_rows: list[dict[str, Any]],
    analysis_master_rows: list[dict[str, Any]],
    default_project: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map an Arash/MouseBytes-style source-of-truth table onto Atlas session IDs.

    Preferred input columns are AnimalID, S_ID/sessionInfoName, Date_Time,
    chronological day, and Age/Timepoint_Months. If Atlas_Master_* columns
    already exist, rows are passed through with light normalization.
    """
    if not selection_rows:
        return [], []

    mapped = []
    audit = []
    probe_rows = [
        r for r in analysis_master_rows
        if txt(r.get("Session_Type_Hint")).lower() == "probe 2b"
        and is_yes(r.get("Include_Primary_Analysis", "YES"))
    ]
    by_animal = defaultdict(list)
    for row in probe_rows:
        by_animal[(project_text(row).casefold(), animal_text(row).casefold())].append(row)
        by_animal[("", animal_text(row).casefold())].append(row)
    by_order = {}
    for (project_key, animal_key), rows in list(by_animal.items()):
        if not project_key:
            continue
        clusters = cluster_sessions(rows, 7.0)
        valid_clusters = [c for c in clusters if len(c) >= 4]
        for block_index, cluster in enumerate(valid_clusters, 1):
            tp_auto = {1: 6, 2: 9, 3: 12}.get(block_index)
            if not tp_auto:
                continue
            for session_index, cand in enumerate(sorted(cluster, key=lambda z: parse_dt(z.get("Session_DateTime")) or datetime.min), 1):
                by_order[(project_key, animal_key, tp_auto, session_index)] = cand

    for source_index, row in enumerate(selection_rows, 1):
        if not is_selected_session(row):
            continue
        if txt(row.get("Atlas_Master_SID")) and txt(row.get("Atlas_Master_Database_Fingerprint")):
            rr = row.copy()
            rr.setdefault("Project", selection_project_text(row, default_project) or project_text(row))
            rr["Timepoint_Months"] = txt(selection_timepoint(row) or row.get("Timepoint_Months") or row.get("Age"))
            rr["Selection_Order"] = txt(selection_order(row, source_index))
            rr["Source_Chronological_Day"] = txt(row.get("chronological day") or row.get("Chronological_Day") or rr["Selection_Order"])
            mapped.append(rr)
            audit.append({**row, "Source_Row": source_index, "Atlas_Master_Match": "ALREADY_MAPPED", "Atlas_Master_Match_Count": 1})
            continue

        animal = selection_animal_text(row)
        project = selection_project_text(row, default_project)
        tp = selection_timepoint(row)
        order = selection_order(row, source_index)
        sid_candidates = selection_sid_candidates(row)
        source_dt = selection_datetime(row)
        candidates = list(by_animal.get((project.casefold(), animal.casefold()), []))
        if not candidates and project:
            candidates = list(by_animal.get(("", animal.casefold()), []))

        scored = []
        for cand in candidates:
            score = 0
            reasons = []
            cand_sid = sid_text(cand.get("SID"))
            if cand_sid and cand_sid in sid_candidates:
                score += 100
                reasons.append("SID")
            cand_dt = parse_dt(cand.get("Session_DateTime"))
            if source_dt and cand_dt:
                delta_days = abs((cand_dt.date() - source_dt.date()).days)
                if delta_days == 0:
                    score += 80
                    reasons.append("DATE_EXACT")
                elif delta_days <= 1:
                    score += 40
                    reasons.append("DATE_WITHIN_1_DAY")
            if tp and num(cand.get("Timepoint_Months")) and int(float(cand.get("Timepoint_Months"))) == tp:
                score += 10
                reasons.append("TIMEPOINT")
            if score:
                scored.append((score, len(reasons), cand, "+".join(reasons)))
        if tp and order:
            order_match = by_order.get((project.casefold(), animal.casefold(), tp, order))
            if order_match:
                scored.append((60, 1, order_match, "ANIMAL_TIMEPOINT_CHRONOLOGICAL_DAY"))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best = scored[0] if scored else None
        matched = best is not None and best[0] >= 40
        audit_row = row.copy()
        audit_row.update({
            "Source_Row": source_index,
            "Selection_Animal_ID": animal,
            "Selection_Project": project,
            "Selection_Timepoint_Months": tp or "",
            "Selection_Order": order,
            "Selection_SID_Candidates": "|".join(sorted(sid_candidates)),
            "Selection_DateTime_Parsed": source_dt.isoformat() if source_dt else "",
            "Atlas_Master_Match": "MATCHED" if matched else "MISSING_IN_ATLAS_MASTER",
            "Atlas_Master_Match_Count": len(scored),
            "Atlas_Master_Match_Method": best[3] if matched else "",
        })
        if matched:
            cand = best[2]
            rr = row.copy()
            rr["Project"] = project_text(cand)
            rr["AnimalID"] = animal_text(cand)
            rr["Timepoint_Months"] = tp or cand.get("Timepoint_Months") or ""
            rr["Selection_Order"] = order
            rr["Source_Chronological_Day"] = txt(row.get("chronological day") or row.get("Chronological_Day") or order)
            rr["Atlas_Master_SID"] = txt(cand.get("SID"))
            rr["Atlas_Master_Database_Fingerprint"] = txt(cand.get("Database_Fingerprint"))
            rr["Atlas_Master_Session_DateTime"] = txt(cand.get("Session_DateTime"))
            rr["Atlas_Master_Source_Database"] = txt(cand.get("Source_Database"))
            mapped.append(rr)
            audit_row.update({
                "Atlas_Master_SID": rr["Atlas_Master_SID"],
                "Atlas_Master_Database_Fingerprint": rr["Atlas_Master_Database_Fingerprint"],
                "Atlas_Master_Session_DateTime": rr["Atlas_Master_Session_DateTime"],
                "Atlas_Master_Source_Database": rr["Atlas_Master_Source_Database"],
            })
        audit.append(audit_row)
    return mapped, audit

def is_yes(v): return txt(v).upper() in {"YES","Y","TRUE","1"}

def norm_sd(v):
    x=num(v)
    if x is None: return None
    # Atlas stores seconds; tolerate milliseconds just in case.
    if x>20: x=x/1000.0
    for t in (2.0,1.0,0.5,0.2):
        if abs(x-t)<0.03: return t
    return round(x,4)



def find_metadata_csv(reports: Path) -> Path | None:
    """Locate the Atlas animal metadata table beside the session reports.

    Prefer the canonical filename; tolerate duplicate-safe Windows/download suffixes
    so a copied reports folder still works.
    """
    canonical = reports / "ATLAS_ANIMAL_METADATA.csv"
    if canonical.exists():
        return canonical
    candidates = sorted(reports.glob("ATLAS_ANIMAL_METADATA*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None

def find_selection_csv(reports: Path) -> Path | None:
    """Find an optional exact Probe 2b session whitelist beside Atlas reports."""
    for name in [
        "PROBE2B_SESSION_SELECTION_REVIEW.xlsx",
        "ATLAS_PROBE2B_SESSION_SELECTIONS.xlsx",
        "ATLAS_PROBE2B_SESSION_SELECTIONS.csv",
    ]:
        canonical = reports / name
        if canonical.exists():
            return canonical
    candidates = sorted(
        list(reports.glob("PROBE2B_SESSION_SELECTION_REVIEW*.xlsx"))
        + list(reports.glob("ATLAS_PROBE2B_SESSION_SELECTIONS*.xlsx"))
        + list(reports.glob("ATLAS_PROBE2B_SESSION_SELECTIONS*.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None

def find_reconciliation_workbook(atlas_dir: Path, reports: Path) -> Path | None:
    """Find the human-reviewed KEEP/EXCLUDE/REMAP decision workbook."""
    candidates = [
        reports / "ATLAS_RECONCILIATION_DECISIONS.xlsx",
        atlas_dir / "ATLAS_RECONCILIATION_DECISIONS.xlsx",
        atlas_dir / "reports" / "ATLAS_RECONCILIATION_DECISIONS.xlsx",
    ]
    for path in candidates:
        if path.exists():
            return path
    hits = []
    for folder in {reports, atlas_dir, atlas_dir / "reports"}:
        if folder.exists():
            hits.extend(folder.glob("ATLAS_RECONCILIATION_DECISIONS*.xlsx"))
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)

def read_decision_workbook(path: Path) -> list[dict[str, Any]]:
    """Read the Decisions sheet from ATLAS_RECONCILIATION_DECISIONS.xlsx."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required to read ATLAS_RECONCILIATION_DECISIONS.xlsx. "
            "Run Install_or_Update_Python_Packages.bat, then run the extractor again."
        ) from exc

    wb = load_workbook(path, data_only=True, read_only=True)
    sheet_name = "Decisions" if "Decisions" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]
    headers = [txt(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = []
    for values in ws.iter_rows(min_row=2, values_only=True):
        row = {headers[i]: values[i] for i in range(min(len(headers), len(values))) if headers[i]}
        if txt(row.get("Atlas_DB_Animal_ID")) or txt(row.get("Animal_ID")):
            rows.append(row)
    return rows

def decision_key(project: str, animal: str) -> tuple[str, str]:
    return (txt(project).casefold(), txt(animal).casefold())

def build_decision_maps(decision_rows: list[dict[str, Any]]):
    maps = {
        "keep": {},
        "exclude": {},
        "remap": {},
        "unresolved": {},
        "all": {},
    }
    for row in decision_rows:
        animal = txt(row.get("Atlas_DB_Animal_ID") or row.get("Animal_ID"))
        project = txt(row.get("Atlas_Project_Hint") or row.get("Final_Project_Group") or row.get("Project_Hint") or row.get("Project"))
        if not animal or not project:
            continue
        decision = txt(row.get("Decision")).upper()
        key = decision_key(project, animal)
        maps["all"][key] = row
        if decision == "KEEP":
            maps["keep"][key] = row
        elif decision == "EXCLUDE":
            maps["exclude"][key] = row
        elif decision == "REMAP":
            maps["remap"][key] = row
        else:
            # Blank and UNSURE are intentionally not treated as clean analysis animals.
            maps["unresolved"][key] = row
    return maps

def apply_final_decision_metadata(row: dict[str, Any], decision_row: dict[str, Any]) -> None:
    mapping = {
        "Final_Project_Group": ("Project_Hint", "Project_Group", "Project"),
        "Final_Cohort": ("Cohort",),
        "Final_Sex": ("Sex",),
        "Final_Genotype": ("Genotype", "Strain"),
        "Final_Treatment": ("Treatment",),
    }
    for source, targets in mapping.items():
        value = txt(decision_row.get(source))
        if not value:
            continue
        for target in targets:
            row[target] = value
    row["Metadata_Match_Status"] = "MATCHED_BY_RECONCILIATION"

def apply_reconciliation_decisions(master_rows: list[dict[str, Any]], decision_rows: list[dict[str, Any]]):
    """Apply KEEP/EXCLUDE/REMAP decisions before analysis extraction.

    The Atlas session master remains untouched on disk. This function returns
    patched in-memory rows plus an audit table that is written beside outputs.
    """
    maps = build_decision_maps(decision_rows)
    remap_targets = {
        key: txt(row.get("Correct_Animal_ID"))
        for key, row in maps["remap"].items()
        if txt(row.get("Correct_Animal_ID"))
    }
    output = []
    audit = []
    counts = defaultdict(int)

    for row0 in master_rows:
        row = row0.copy()
        project = txt(row.get("Project_Hint") or row.get("Project_Group") or row.get("Project"))
        animal = txt(row.get("Animal_ID") or row.get("AnimalID") or row.get("Animal ID"))
        key = decision_key(project, animal)
        action = "NO_DECISION_ROW"
        include = True
        reason = ""
        decision_row = None

        if key in maps["exclude"]:
            decision_row = maps["exclude"][key]
            action = "EXCLUDE"
            include = False
            reason = "Excluded by ATLAS_RECONCILIATION_DECISIONS.xlsx"
        elif key in maps["remap"]:
            decision_row = maps["remap"][key]
            corrected = remap_targets.get(key)
            if corrected:
                action = "REMAP"
                row["Original_Animal_ID"] = animal
                row["Animal_ID"] = corrected
                row["AnimalID"] = corrected
                apply_final_decision_metadata(row, decision_row)
                reason = f"Remapped {animal} to {corrected}"
            else:
                action = "REMAP_MISSING_CORRECT_ID"
                include = False
                reason = "REMAP selected but Correct_Animal_ID is blank"
        elif key in maps["keep"]:
            decision_row = maps["keep"][key]
            action = "KEEP"
            apply_final_decision_metadata(row, decision_row)
            reason = "Kept by reconciliation decision"
        elif key in maps["unresolved"]:
            decision_row = maps["unresolved"][key]
            action = "UNRESOLVED"
            include = False
            reason = "Decision is blank or UNSURE"

        row["Reconciliation_Action"] = action
        row["Reconciliation_Include"] = "YES" if include else "NO"
        row["Reconciliation_Reason"] = reason
        if include:
            output.append(row)
        counts[action] += 1
        if action != "NO_DECISION_ROW":
            audit.append({
                "Project": project,
                "Original_Animal_ID": animal,
                "Final_Animal_ID": txt(row.get("Animal_ID") or row.get("AnimalID")),
                "Action": action,
                "Include_In_Analysis": "YES" if include else "NO",
                "Reason": reason,
                "Final_Project_Group": txt(decision_row.get("Final_Project_Group")) if decision_row else "",
                "Final_Cohort": txt(decision_row.get("Final_Cohort")) if decision_row else "",
                "Final_Sex": txt(decision_row.get("Final_Sex")) if decision_row else "",
                "Final_Genotype": txt(decision_row.get("Final_Genotype")) if decision_row else "",
                "Final_Treatment": txt(decision_row.get("Final_Treatment")) if decision_row else "",
                "Reviewer_Notes": txt(decision_row.get("Reviewer_Notes")) if decision_row else "",
            })

    return output, audit, dict(counts)


def merge_animal_metadata(master_rows: list[dict[str,Any]], metadata_rows: list[dict[str,Any]]):
    """Attach finalized animal metadata using Project + Animal ID.

    This is deliberately project-aware because the same Animal ID may represent
    different animals in the Vaccine and Lecanemab projects. Existing nonblank
    session values are preserved; finalized animal metadata fills/overrides the
    group fields used for analysis and compatibility exports.
    """
    lookup={}
    for m in metadata_rows:
        project=txt(m.get("Project_Group") or m.get("Project_Hint") or m.get("Project"))
        animal=txt(m.get("AnimalID") or m.get("Animal_ID") or m.get("Animal ID"))
        if project and animal:
            lookup[(project.casefold(),animal.casefold())]=m
    fields=("Cohort","Sex","Genotype","Treatment","Strain")
    out=[]; matched=0
    for r0 in master_rows:
        r=r0.copy()
        project=txt(r.get("Project_Hint") or r.get("Project_Group") or r.get("Project"))
        animal=txt(r.get("Animal_ID") or r.get("AnimalID") or r.get("Animal ID"))
        m=lookup.get((project.casefold(),animal.casefold()))
        if m is not None:
            matched += 1
            for f in fields:
                mv=txt(m.get(f))
                if mv:
                    r[f]=mv
            # Strain is intentionally represented by genotype for these cohorts
            # when the metadata source does not carry a separate strain value.
            if not txt(r.get("Strain")) and txt(r.get("Genotype")):
                r["Strain"]=txt(r.get("Genotype"))
            r["Metadata_Match_Status"]="MATCHED"
        else:
            r["Metadata_Match_Status"]="UNMATCHED"
        out.append(r)
    return out, matched, len(master_rows)-matched

# ------------------------ session manifest -------------------------
def build_manifest(master_rows, selection_rows: list[dict[str, Any]] | None = None):
    """Build the Probe 2b manifest.

    When a source-of-truth/session-review whitelist is supplied, exact USE
    sessions are taken from that file. Any session not explicitly matched to a
    USE row remains available to the automatic date-cluster fallback, so a
    partial review workbook cannot accidentally discard other animals or other
    timepoints from the same animal.
    """
    probe = [
        r.copy() for r in master_rows
        if txt(r.get("Session_Type_Hint")).lower() == "probe 2b"
        and is_yes(r.get("Include_Primary_Analysis", "YES"))
    ]
    selection_map = {}
    for row in selection_rows or []:
        if not is_selected_session(row):
            continue
        selection_map[selection_key(row)] = row

    by_all = defaultdict(list)
    selected_keys = set()
    selected_block_tps = defaultdict(set)
    by_auto = defaultdict(list)
    by_selected = defaultdict(list)
    for row in probe:
        project = project_text(row)
        animal = animal_text(row)
        by_all[(project, animal)].append(row)
        selected = selection_map.get(selection_key(row)) if selection_map else None
        if selected:
            selected_keys.add(selection_key(row))
            selected_tp = selection_timepoint(selected)
            if selected_tp:
                selected_block_tps[(project, animal)].add(selected_tp)
            rr = row.copy()
            rr["_Source_Timepoint_Months"] = txt(selected.get("Timepoint_Months"))
            rr["_Source_Selection_Order"] = txt(selected.get("Selection_Order"))
            rr["_Source_Chronological_Day"] = txt(selected.get("Source_Chronological_Day"))
            by_selected[(project, animal, txt(selected.get("Timepoint_Months")))].append(rr)
            continue
        by_auto[(project, animal)].append(row)

    manifest = []
    qc = []

    # Exact source-of-truth selection path.
    for (project, animal, tp_text), rows in sorted(by_selected.items()):
        tp = int(float(tp_text)) if tp_text else None
        rows = sorted(rows, key=lambda r: int(float(txt(r.get("_Source_Selection_Order")) or 9999)))
        count_ok = len(rows) == 4
        block_number = {6: 1, 9: 2, 12: 3}.get(tp)
        for si, row in enumerate(rows, 1):
            rr = row.copy()
            rr["Probe_Block_Number"] = block_number or ""
            rr["Timepoint_Months"] = tp or ""
            rr["Timepoint_Label"] = f"{tp} months" if tp else "Unassigned"
            rr["Probe_Session_Number"] = si
            rr["Selection_Mode"] = "SOURCE_WHITELIST"
            rr["Source_Timepoint_Months"] = rr.pop("_Source_Timepoint_Months", "")
            rr["Source_Selection_Order"] = rr.pop("_Source_Selection_Order", "")
            rr["Source_Chronological_Day"] = rr.pop("_Source_Chronological_Day", "")
            design_ok = not (
                project.casefold() == "lecanemab"
                and txt(rr.get("Cohort")).lower().replace(" ", "") in {"cohort1", "1"}
                and tp == 12
            )
            rr["Design_Eligible"] = "YES" if design_ok and count_ok and tp in {6, 9, 12} else "NO"
            if not count_ok:
                rr["Design_Exclusion_Reason"] = f"Source whitelist contains {len(rows)} sessions; exactly 4 required"
            elif not design_ok and tp == 12:
                rr["Design_Exclusion_Reason"] = "Lecanemab Cohort 1 treatment stopped after 9 months"
            elif tp not in {6, 9, 12}:
                rr["Design_Exclusion_Reason"] = "Unassigned timepoint block"
            else:
                rr["Design_Exclusion_Reason"] = ""
            manifest.append(rr)
        qc.append({
            "Project": project,
            "Animal_ID": animal,
            "Probe_Sessions_Final": len(rows),
            "Chronological_Clusters": "SOURCE_WHITELIST",
            "Valid_Clusters_ge4": 1 if count_ok else 0,
            "Assigned_6_9_12": 1 if tp in {6, 9, 12} else 0,
            "Selection_Mode": "SOURCE_WHITELIST",
            "QC_Status": "OK" if count_ok and tp in {6, 9, 12} else "CHECK",
        })

    # Automatic fallback for rows not explicitly USE-selected. Cluster the full
    # animal timeline first so a partial review workbook cannot renumber the
    # remaining 9/12-month blocks as 6/9 months.
    for (project, animal), all_rows in sorted(by_all.items()):
        auto_rows = by_auto.get((project, animal), [])
        if not auto_rows:
            continue
        auto_key_set = {selection_key(r) for r in auto_rows}
        clusters = cluster_sessions(all_rows, 7.0)
        valid_cluster_infos = [
            (ci, c) for ci, c in enumerate(clusters, 1)
            if len(c) >= 4
        ]
        auto_valid_cluster_infos = []
        for ci, cluster in valid_cluster_infos:
            tp = {1: 6, 2: 9, 3: 12}.get(ci)
            if tp in selected_block_tps.get((project, animal), set()):
                continue
            auto_cluster = [r for r in cluster if selection_key(r) in auto_key_set]
            if auto_cluster:
                auto_valid_cluster_infos.append((ci, auto_cluster))
        for ci, cluster in auto_valid_cluster_infos:
            tp = {1: 6, 2: 9, 3: 12}.get(ci)
            exact_four = len(cluster) == 4
            source_tps = sorted({x for x in (row_source_timepoint(r) for r in cluster) if x is not None})
            source_tp_conflict = bool(tp in {6, 9, 12} and source_tps and source_tps != [tp])
            for si, row in enumerate(sorted(cluster, key=lambda z: parse_dt(z.get("Session_DateTime")) or datetime.min), 1):
                rr = row.copy()
                rr["Probe_Block_Number"] = ci
                rr["Timepoint_Months"] = tp or ""
                rr["Timepoint_Label"] = f"{tp} months" if tp else "Unassigned"
                rr["Probe_Session_Number"] = si
                rr["Selection_Mode"] = "AUTOMATIC_DATE_CLUSTER"
                rr["Source_Timepoint_Months"] = ",".join(str(x) for x in source_tps)
                design_ok = not (
                    project.casefold() == "lecanemab"
                    and txt(row.get("Cohort")).lower().replace(" ", "") in {"cohort1", "1"}
                    and tp == 12
                )
                rr["Design_Eligible"] = "YES" if design_ok and tp in {6, 9, 12} and exact_four and not source_tp_conflict else "NO"
                if not design_ok and tp == 12:
                    rr["Design_Exclusion_Reason"] = "Lecanemab Cohort 1 treatment stopped after 9 months"
                elif len(cluster) > 4:
                    rr["Design_Exclusion_Reason"] = (
                        f"Timepoint block contains {len(cluster)} Probe 2b sessions; "
                        "review required to choose exactly 4 USE sessions"
                    )
                elif source_tp_conflict:
                    rr["Design_Exclusion_Reason"] = (
                        f"Automatic cluster assigned {tp} months but source rows indicate "
                        f"{','.join(str(x) for x in source_tps)} months; review Timepoint_Months"
                    )
                elif tp not in {6, 9, 12}:
                    rr["Design_Exclusion_Reason"] = "Unassigned timepoint block"
                else:
                    rr["Design_Exclusion_Reason"] = ""
                manifest.append(rr)
        qc.append({
            "Project": project,
            "Animal_ID": animal,
            "Probe_Sessions_Final": len(auto_rows),
            "Chronological_Clusters": "+".join(str(len(c)) for _, c in auto_valid_cluster_infos) or "+".join(str(len(c)) for c in clusters),
            "Valid_Clusters_ge4": len(auto_valid_cluster_infos),
            "Assigned_6_9_12": sum(1 for ci, _c in auto_valid_cluster_infos if {1: 6, 2: 9, 3: 12}.get(ci) in {6, 9, 12}),
            "Selection_Mode": "AUTOMATIC_DATE_CLUSTER",
            "QC_Status": "OK" if auto_valid_cluster_infos and all(
                len(c) == 4
                and not (
                    {x for x in (row_source_timepoint(r) for r in c) if x is not None}
                    and {x for x in (row_source_timepoint(r) for r in c) if x is not None} != {{1: 6, 2: 9, 3: 12}.get(i)}
                )
                for i, c in auto_valid_cluster_infos
            ) else "CHECK",
        })
    return manifest, qc

def make_timepoint_assignment_detail(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize each assigned Probe 2b animal/timepoint block for QC review."""
    blocks = defaultdict(list)
    for row in manifest:
        key = (
            txt(row.get("Project_Hint") or row.get("Project_Group") or row.get("Project")),
            txt(row.get("Animal_ID") or row.get("AnimalID")),
            txt(row.get("Timepoint_Months")),
            txt(row.get("Probe_Block_Number")),
        )
        blocks[key].append(row)

    detail = []
    source_tp_by_animal = defaultdict(list)
    for (project, animal, tp_text, block_text), rows in sorted(blocks.items(), key=lambda item: (item[0][0], item[0][1], float(item[0][2] or 9999), float(item[0][3] or 9999))):
        assigned_tp = int(float(tp_text)) if tp_text else None
        source_tps = sorted({
            str(x).strip()
            for row in rows
            for x in txt(row.get("Source_Timepoint_Months") or row_source_timepoint(row)).replace(";", ",").split(",")
            if str(x).strip()
        }, key=lambda z: float(z) if z.replace(".", "", 1).isdigit() else 9999)
        source_tp_by_animal[(project, animal)].append((assigned_tp, tuple(source_tps)))

    duplicate_source_tps = defaultdict(set)
    for animal_key, pairs in source_tp_by_animal.items():
        seen = defaultdict(set)
        for assigned_tp, source_tps in pairs:
            for source_tp in source_tps:
                seen[source_tp].add(assigned_tp)
        for source_tp, assigned_tps in seen.items():
            if len({tp for tp in assigned_tps if tp is not None}) > 1:
                duplicate_source_tps[animal_key].add(source_tp)

    for (project, animal, tp_text, block_text), rows in sorted(blocks.items(), key=lambda item: (item[0][0], item[0][1], float(item[0][2] or 9999), float(item[0][3] or 9999))):
        rows = sorted(rows, key=lambda r: parse_dt(r.get("Session_DateTime")) or datetime.min)
        assigned_tp = int(float(tp_text)) if tp_text else None
        source_tps = sorted({
            str(x).strip()
            for row in rows
            for x in txt(row.get("Source_Timepoint_Months") or row_source_timepoint(row)).replace(";", ",").split(",")
            if str(x).strip()
        }, key=lambda z: float(z) if z.replace(".", "", 1).isdigit() else 9999)
        source_tp_nums = {
            int(float(x)) for x in source_tps
            if x.replace(".", "", 1).isdigit()
        }
        reasons = sorted({txt(r.get("Design_Exclusion_Reason")) for r in rows if txt(r.get("Design_Exclusion_Reason"))})
        duplicate_sources = sorted(set(source_tps) & duplicate_source_tps[(project, animal)])
        if assigned_tp and source_tp_nums and source_tp_nums != {assigned_tp}:
            source_status = "MISMATCH"
            qc_status = "CHECK"
            qc_reason = f"Assigned {assigned_tp} months but source rows indicate {','.join(source_tps)} months"
            action = "Edit Timepoint_Months in PROBE2B_SESSION_SELECTION_REVIEW.xlsx/source selection so this date block has the intended age."
        elif duplicate_sources:
            source_status = "DUPLICATE_SOURCE_TIMEPOINT"
            qc_status = "CHECK"
            qc_reason = f"Source timepoint {','.join(duplicate_sources)} appears in multiple chronological blocks for this animal"
            action = "Review all blocks for this animal and assign exactly one 4-session block to each intended Timepoint_Months value."
        elif reasons:
            source_status = "OK" if source_tps else "MISSING"
            qc_status = "CHECK"
            qc_reason = "; ".join(reasons)
            action = "Resolve the review reason, then rerun the extractor."
        else:
            source_status = "OK" if source_tps else "MISSING"
            qc_status = "OK"
            qc_reason = ""
            action = ""
        detail.append({
            "Project": project,
            "Animal_ID": animal,
            "Selection_Mode": txt(rows[0].get("Selection_Mode")) or "UNKNOWN",
            "Assigned_Timepoint_Months": assigned_tp or "",
            "Probe_Block_Number": block_text,
            "Sessions_In_Block": len(rows),
            "Session_Date_Start": (parse_dt(rows[0].get("Session_DateTime")).isoformat(sep=" ") if rows and parse_dt(rows[0].get("Session_DateTime")) else ""),
            "Session_Date_End": (parse_dt(rows[-1].get("Session_DateTime")).isoformat(sep=" ") if rows and parse_dt(rows[-1].get("Session_DateTime")) else ""),
            "Session_SIDs": ",".join(txt(r.get("SID") or r.get("S_ID")) for r in rows),
            "Probe_Session_Numbers": ",".join(txt(r.get("Probe_Session_Number")) for r in rows),
            "Source_Timepoint_Months": ",".join(source_tps),
            "Source_Timepoint_Status": source_status,
            "QC_Status": qc_status,
            "QC_Reason": qc_reason,
            "Suggested_Action": action,
        })
    return detail

def make_probe_session_selection_review_rows(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows needing manual Probe 2b session choice before analysis."""
    blocks = defaultdict(list)
    for row in manifest:
        reason = txt(row.get("Design_Exclusion_Reason"))
        needs_review = (
            "review required to choose exactly 4 USE sessions" in reason
            or "review Timepoint_Months" in reason
            or "Unassigned timepoint block" in reason
        )
        if not needs_review:
            continue
        key = (
            txt(row.get("Project_Hint") or row.get("Project_Group") or row.get("Project")),
            txt(row.get("Animal_ID") or row.get("AnimalID")),
            txt(row.get("Timepoint_Months")),
        )
        blocks[key].append(row)

    review_rows = []
    for (_project, _animal, _tp), rows in sorted(blocks.items()):
        rows = sorted(rows, key=lambda r: parse_dt(r.get("Session_DateTime")) or datetime.min)
        for order, row in enumerate(rows, 1):
            review_rows.append({
                "Selected": "",
                "Project": txt(row.get("Project_Hint") or row.get("Project_Group") or row.get("Project")),
                "AnimalID": txt(row.get("Animal_ID") or row.get("AnimalID")),
                "Timepoint_Months": txt(row.get("Timepoint_Months")),
                "Selection_Order": order,
                "Session_DateTime": txt(row.get("Session_DateTime")),
                "SID": txt(row.get("SID")),
                "Source_Database": txt(row.get("Source_Database")),
                "Atlas_Master_SID": txt(row.get("SID")),
                "Atlas_Master_Database_Fingerprint": txt(row.get("Database_Fingerprint")),
                "Atlas_Master_Session_DateTime": txt(row.get("Session_DateTime")),
                "Atlas_Master_Source_Database": txt(row.get("Source_Database")),
                "Review_Reason": txt(row.get("Design_Exclusion_Reason")),
                "Reviewer_Notes": "",
            })
    return review_rows



# ---------------------- matched Stage 4 baseline ----------------------
def build_stage4_manifest(master_rows: list[dict[str,Any]], probe_manifest: list[dict[str,Any]]):
    """Select up to the last four Stage 4 sessions immediately before each Probe block.

    Baseline availability never affects Probe 2b inclusion. For later timepoints,
    Stage 4 sessions must occur after the end of the preceding Probe block so an
    earlier baseline cannot be reused at multiple timepoints.
    """
    stage4_by=defaultdict(list)
    for r in master_rows:
        if txt(r.get("Session_Type_Hint")).lower()=="stage 4" and is_yes(r.get("Include_Primary_Analysis","YES")):
            stage4_by[(txt(r.get("Project_Hint")),txt(r.get("Animal_ID")))].append(r.copy())
    for k in stage4_by:
        stage4_by[k].sort(key=lambda r: parse_dt(r.get("Session_DateTime")) or datetime.min)

    probe_by=defaultdict(list)
    for r in probe_manifest:
        if r.get("Timepoint_Months") in {6,9,12} and int(r.get("Probe_Session_Number") or 0)<=4:
            probe_by[(txt(r.get("Project_Hint")),txt(r.get("Animal_ID")),int(r.get("Probe_Block_Number") or 0))].append(r)

    selected=[]; qc=[]
    animal_blocks=defaultdict(list)
    for (project,animal,block), rows in probe_by.items():
        animal_blocks[(project,animal)].append((block,rows))

    for (project,animal), blocks in sorted(animal_blocks.items()):
        blocks=sorted(blocks,key=lambda x:x[0])
        prev_probe_end=None
        candidates_all=stage4_by.get((project,animal),[])
        for block,prows in blocks:
            prows=sorted(prows,key=lambda r: parse_dt(r.get("Session_DateTime")) or datetime.min)
            first_probe_dt=parse_dt(prows[0].get("Session_DateTime")) if prows else None
            last_probe_dt=parse_dt(prows[-1].get("Session_DateTime")) if prows else None
            tp=prows[0].get("Timepoint_Months") if prows else ""
            candidates=[]
            if first_probe_dt is not None:
                for s4 in candidates_all:
                    dt=parse_dt(s4.get("Session_DateTime"))
                    if dt is None or dt>=first_probe_dt: continue
                    if prev_probe_end is not None and dt<=prev_probe_end: continue
                    candidates.append(s4)
            chosen=candidates[-4:]
            count=len(chosen)
            status="FULL_4" if count>=4 else "PARTIAL_3" if count==3 else "PARTIAL_2" if count==2 else "LIMITED_1" if count==1 else "NO_BASELINE_FOUND"
            for i,s4 in enumerate(chosen,1):
                rr=s4.copy()
                # Metadata/timepoint are inherited from the matched Probe block if absent on Stage 4.
                ref=prows[0]
                for col in ["Cohort","Sex","Genotype","Treatment","Strain"]:
                    if not txt(rr.get(col)): rr[col]=ref.get(col,"")
                rr["Matched_Probe_Block_Number"]=block
                rr["Timepoint_Months"]=tp
                rr["Timepoint_Label"]=f"{tp} months" if tp else ""
                rr["Baseline_Day_Number"]=i
                rr["Baseline_Sessions_Found_In_Window"]=len(candidates)
                rr["Baseline_Sessions_Used"]=count
                rr["Baseline_Status"]=status
                rr["Matched_First_Probe_DateTime"]=txt(prows[0].get("Session_DateTime"))
                rr["Design_Eligible"]="YES"
                rr["Probe_Session_Number"]=i  # temporary compatibility for shared trial enrichment
                selected.append(rr)
            qc.append({
                "Project":project,"Animal_ID":animal,"Cohort":txt(prows[0].get("Cohort")),
                "Sex":txt(prows[0].get("Sex")),"Genotype":txt(prows[0].get("Genotype")),"Treatment":txt(prows[0].get("Treatment")),
                "Timepoint_Months":tp,"Probe_Block_Number":block,
                "First_Probe_DateTime":txt(prows[0].get("Session_DateTime")),
                "Stage4_Found_In_Timepoint_Window":len(candidates),"Stage4_Used":count,
                "Baseline_Status":status,
                "Rule":"Last up to 4 Stage 4 sessions after previous Probe block and before current Probe block"
            })
            if last_probe_dt is not None: prev_probe_end=last_probe_dt
    return selected,qc


def enrich_stage4_trials(raw_trials, stage4_manifest):
    rows=enrich_trials(raw_trials, stage4_manifest)
    lookup={session_key(r):r for r in stage4_manifest}
    for r in rows:
        s=lookup.get((txt(r.get("Database_Fingerprint")),txt(r.get("SID"))),{})
        r["Baseline_Day_Number"]=s.get("Baseline_Day_Number",r.get("Probe_Session_Number"))
        r["Baseline_Status"]=s.get("Baseline_Status","")
        r["Baseline_Sessions_Used"]=s.get("Baseline_Sessions_Used","")
        r["Matched_Probe_Block_Number"]=s.get("Matched_Probe_Block_Number","")
        r["Matched_First_Probe_DateTime"]=s.get("Matched_First_Probe_DateTime","")
        r.pop("Probe_Session_Number",None)
    return rows


def make_stage4_summaries(trials):
    by=defaultdict(list)
    for r in trials: by[(r["Database_Fingerprint"],r["SID"])].append(r)
    session_rows=[]
    for _,g in sorted(by.items(),key=lambda kv:str(kv[0])):
        x=g[0]
        b={k:x.get(k) for k in ["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Source_Database","SID","Session_DateTime","Baseline_Day_Number","Baseline_Status","Baseline_Sessions_Used","Matched_Probe_Block_Number","Matched_First_Probe_DateTime"]}
        b["Stimulus_Duration_s"]="ALL"
        session_rows.append(summarize_group(g,b))
    av=[]; avgby=defaultdict(list)
    for r in session_rows: avgby[(r["Project"],r["Animal_ID"],r["Timepoint_Months"])].append(r)
    exclude={"Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Source_Database","SID","Session_DateTime","Baseline_Day_Number","Baseline_Status","Baseline_Sessions_Used","Matched_Probe_Block_Number","Matched_First_Probe_DateTime","Stimulus_Duration_s"}
    metrics=[k for k in session_rows[0] if k not in exclude] if session_rows else []
    for _,g in sorted(avgby.items(),key=lambda kv:str(kv[0])):
        b={k:g[0].get(k) for k in ["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Baseline_Status"]}
        b["Baseline_Sessions_Averaged"]=len(g)
        for c in metrics: b[c]=mean(x.get(c) for x in g)
        av.append(b)
    return session_rows,av


def make_stage4_iti_summaries(trials):
    """Stage 4 counterpart of Probe 2b ITI-stratified session and decile metrics.

    Session deciles are computed across the FULL Stage 4 session before splitting
    by ITI, exactly like Probe 2b. Preserve missing ITI as an audit count rather
    than misassigning events to one of the two conditions.
    """
    id_fields = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
                 "Timepoint_Months", "Timepoint_Label", "Source_Database", "SID",
                 "Session_DateTime", "Baseline_Day_Number", "Baseline_Status",
                 "Baseline_Sessions_Used", "Matched_Probe_Block_Number", "Matched_First_Probe_DateTime"]
    by_session = defaultdict(list)
    for r in trials:
        by_session[(r["Database_Fingerprint"], r["SID"])].append(r)
    session_rows, decile_rows, qc_rows = [], [], []
    for key, full in sorted(by_session.items(), key=lambda kv: str(kv[0])):
        ref = full[0]
        identity = {k: ref.get(k) for k in id_fields}
        counts = {iti: sum(1 for r in full if num(r.get("Current_ITI_s")) is not None and abs(num(r.get("Current_ITI_s"))-iti)<.03) for iti in (2.0, 3.0)}
        qc_rows.append({**identity, "Trial_Rows": len(full), "ITI_2s_Rows": counts[2.0],
                        "ITI_3s_Rows": counts[3.0], "Unknown_Or_Other_ITI_Rows": len(full)-sum(counts.values()),
                        "ITI_Status": "BOTH" if all(counts.values()) else "ONLY_2S" if counts[2.0] else "ONLY_3S" if counts[3.0] else "NO_VALID_ITI"})
        for iti in (2.0, 3.0):
            group = [r for r in full if num(r.get("Current_ITI_s")) is not None and abs(num(r.get("Current_ITI_s"))-iti)<.03]
            if not group:
                continue
            base = {**identity, "Stimulus_Duration_s": 2.0, "Current_ITI_s": iti}
            session_rows.append(summarize_group(group, base))
            for dec in range(1, 11):
                d = [r for r in group if num(r.get("Session_Progress_Decile")) == dec]
                if d:
                    decile_rows.append(summarize_group(d, {**base, "Session_Progress_Decile": dec,
                                                            "Session_Progress_Percent_Midpoint": dec*10-5}))
    averages = []
    by_animal = defaultdict(list)
    for r in session_rows:
        by_animal[(r["Project"], r["Animal_ID"], r["Timepoint_Months"], r["Current_ITI_s"])].append(r)
    skip = set(id_fields) | {"Stimulus_Duration_s", "Current_ITI_s"}
    for _, group in sorted(by_animal.items(), key=lambda kv: str(kv[0])):
        base = {k:group[0].get(k) for k in ("Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Stimulus_Duration_s","Current_ITI_s")}
        base["Sessions_Averaged"] = len(group)
        for col in group[0]:
            if col not in skip and col not in base and col != "Sessions_Averaged":
                base[col] = mean(r.get(col) for r in group)
        averages.append(base)
    return session_rows, averages, decile_rows, qc_rows


def make_baseline_probe_2s(stage4_avg, probe_avg):
    """Long-format matched 2-s baseline vs Probe table for the baseline-to-probe graphs/models."""
    rows=[]
    for r in stage4_avg:
        rows.append({**r,"Phase":"Stage 4 baseline","Stimulus_Duration_s":2.0})
    for r in probe_avg:
        sd=num(r.get("Stimulus_Duration_s"))
        if sd is None or abs(sd-2.0)>=0.03: continue
        rr=r.copy(); rr["Phase"]="Probe 2b"; rows.append(rr)
    return rows


# -------------------------- trial query ----------------------------
def find_index_db(atlas_dir: Path):
    candidates=[atlas_dir/"cache"/"NMR_ABET_Atlas.sqlite", atlas_dir/"NMR_ABET_Atlas.sqlite"]
    for p in candidates:
        if p.exists(): return p
    hits=list(atlas_dir.rglob("NMR_ABET_Atlas.sqlite"))
    return hits[0] if hits else None

def fetch_trials(db_path: Path, keys: set[tuple[str,str]]):
    conn=sqlite3.connect(str(db_path)); conn.row_factory=sqlite3.Row
    try:
        cols=[r[1] for r in conn.execute("PRAGMA table_info(trials)").fetchall()]
        if not cols: raise RuntimeError("Atlas SQLite has no 'trials' table.")
        out=[]
        # Fetch by fingerprints in batches, filter SID in Python to avoid huge OR expressions.
        fps=sorted({k[0] for k in keys if k[0]})
        for i in range(0,len(fps),500):
            chunk=fps[i:i+500]; ph=",".join("?" for _ in chunk)
            for row in conn.execute(f"SELECT * FROM trials WHERE database_fingerprint IN ({ph})",chunk):
                d=dict(row); k=(txt(d.get("database_fingerprint")),txt(d.get("sid")))
                if k in keys: out.append(d)
        return out
    finally: conn.close()

# ------------------------ trial enrichment -------------------------
def enrich_trials(raw_trials, manifest):
    m={session_key(r):r for r in manifest if txt(r.get("Design_Eligible"))=="YES"}
    rows=[]
    for t in raw_trials:
        k=(txt(t.get("database_fingerprint")),txt(t.get("sid")))
        s=m.get(k)
        if not s: continue
        out={
            "Project":txt(s.get("Project_Hint")),"Animal_ID":txt(s.get("Animal_ID")),"Cohort":txt(s.get("Cohort")),
            "Sex":txt(s.get("Sex")),"Genotype":txt(s.get("Genotype")),"Treatment":txt(s.get("Treatment")),
            "Timepoint_Months":s.get("Timepoint_Months"),"Timepoint_Label":s.get("Timepoint_Label"),
            "Probe_Session_Number":s.get("Probe_Session_Number"),"Source_Database":txt(s.get("Source_Database")),
            "Database_Fingerprint":txt(s.get("Database_Fingerprint")),"SID":txt(s.get("SID")),"Session_DateTime":txt(s.get("Session_DateTime")),
            "Schedule_Name":txt(s.get("Schedule_Name")),"Trial_Index":t.get("trial_index"),"Trial_Counter":t.get("trial_counter"),
            "Stimulus_Onset":t.get("stimulus_onset"),"Outcome_Time":t.get("outcome_time"),"Outcome":txt(t.get("outcome")),
            "Stimulus_Duration_s":norm_sd(t.get("stimulus_duration_s")),"Current_Image":t.get("current_image"),"Correct_Image":t.get("correct_image"),
            "Current_ITI_s":t.get("current_iti_s"),"Correct_Grid_Position":t.get("correct_grid_position"),
            "Hit":int(t.get("hit") or 0),"Miss":int(t.get("miss") or 0),"False_Alarm":int(t.get("false_alarm") or 0),"Correct_Rejection":int(t.get("correct_rejection") or 0),
            "Correction_Trial_Correct_Rejection":int(t.get("correction_trial_correct_rejection") or 0),"Correction_Trial_Mistake":int(t.get("correction_trial_mistake") or 0),
            "Response_Latency_Raw_s":num(t.get("response_latency_s")),"Reward_Retrieval_Latency_Raw_s":num(t.get("reward_retrieval_latency_s")),
        }
        out["Correct_Touch_Latency_Raw_s"] = out["Response_Latency_Raw_s"] if out["Hit"] else None
        out["Incorrect_Touch_Latency_Raw_s"] = out["Response_Latency_Raw_s"] if out["False_Alarm"] else None
        rows.append(out)
    # session-level IQR screening separately by class, min 4 values; raw retained.
    by=defaultdict(list)
    for i,r in enumerate(rows): by[(r["Database_Fingerprint"],r["SID"])].append((i,r))
    for _,items in by.items():
        for rawcol,clean,colflag,prefix in [
            ("Correct_Touch_Latency_Raw_s","Correct_Touch_Latency_IQRclean_s","Correct_Touch_Latency_IQR_Excluded","Correct"),
            ("Incorrect_Touch_Latency_Raw_s","Incorrect_Touch_Latency_IQRclean_s","Incorrect_Touch_Latency_IQR_Excluded","Incorrect"),
            ("Reward_Retrieval_Latency_Raw_s","Reward_Retrieval_Latency_IQRclean_s","Reward_Retrieval_Latency_IQR_Excluded","Reward"),
        ]:
            vals=[r[rawcol] for _,r in items if r[rawcol] is not None]
            lo,hi=iqr_bounds(vals)
            for _,r in items:
                v=r[rawcol]; excl = bool(v is not None and lo is not None and (v<lo or v>hi))
                r[clean]=None if excl else v; r[colflag]=1 if excl else 0; r[f"{prefix}_IQR_Lower_s"]=lo; r[f"{prefix}_IQR_Upper_s"]=hi
        n=len(items)
        ordered=sorted(items,key=lambda x:(num(x[1].get("Trial_Index")) or 0))
        for rank,(_,r) in enumerate(ordered,1):
            r["Session_Progress_Decile"]=min(10,max(1,math.ceil(rank/n*10))) if n else None
            r["Session_Progress_Percent_Midpoint"]=r["Session_Progress_Decile"]*10-5 if n else None
        # next-presentation previous outcome/difficulty context within each session.
        # Atlas uses Trial_Index internally, but each row is one CPT image presentation.
        prev_row=None
        for _,r in ordered:
            prev=prev_row["Outcome"] if prev_row else ""
            r["Previous_Trial_Index"]=prev_row.get("Trial_Index") if prev_row else None
            r["Previous_Image_Presentation_Index"]=r["Previous_Trial_Index"]
            r["Image_Presentation_Index"]=r.get("Trial_Index")
            r["Previous_Stimulus_Duration_s"]=prev_row.get("Stimulus_Duration_s") if prev_row else None
            r["Previous_Trial_Outcome"]=prev
            r["Previous_Trial_Is_Correction"]=int(
                bool(prev_row) and txt(prev).lower().startswith("correction trial")
            )
            r["Current_Trial_Is_Correction"]=int(txt(r.get("Outcome")).lower().startswith("correction trial"))
            r["Previous_Response_Latency_Raw_s"]=prev_row.get("Response_Latency_Raw_s") if prev_row else None
            r["Previous_Reward_Retrieval_Latency_IQRclean_s"]=prev_row.get("Reward_Retrieval_Latency_IQRclean_s") if prev_row else None
            prev_sd=r["Previous_Stimulus_Duration_s"]
            if prev_sd is not None and (abs(float(prev_sd)-0.2)<0.03 or abs(float(prev_sd)-0.5)<0.03):
                r["Previous_Trial_Difficulty_Class"]="After hard previous trial (0.2/0.5 s)"
            elif prev_sd is not None and (abs(float(prev_sd)-1.0)<0.03 or abs(float(prev_sd)-2.0)<0.03):
                r["Previous_Trial_Difficulty_Class"]="After easy previous trial (1.0/2.0 s)"
            else:
                r["Previous_Trial_Difficulty_Class"]=""
            r["Previous_Image_Presentation_Difficulty_Class"]=r["Previous_Trial_Difficulty_Class"]
            if prev in {"Hit","Correct Rejection"}: r["Previous_Outcome_Class"]="After correct trial"
            elif prev in {"Miss","False Alarm","Mistake"}: r["Previous_Outcome_Class"]="After error/miss"
            else: r["Previous_Outcome_Class"]=""
            prev_row=r
    return rows

# --------------------------- summaries -----------------------------
def summarize_group(group: list[dict[str,Any]], base: dict[str,Any]):
    h=sum(r["Hit"] for r in group); m=sum(r["Miss"] for r in group); fa=sum(r["False_Alarm"] for r in group); cr=sum(r["Correct_Rejection"] for r in group)
    out=base.copy(); out.update({"Hits":h,"Misses":m,"False_Alarms":fa,"Correct_Rejections":cr,"Signal_Trials":h+m,"Noise_Trials":fa+cr,"Core_Trials":h+m+fa+cr})
    out.update(rate_metrics(h,m,fa,cr))
    out.update({
        "Mean_Correct_Touch_Latency_Raw_s":mean(r["Correct_Touch_Latency_Raw_s"] for r in group),
        "Mean_Correct_Touch_Latency_IQRclean_s":mean(r["Correct_Touch_Latency_IQRclean_s"] for r in group),
        "Correct_Latency_IQR_Excluded_n":sum(r["Correct_Touch_Latency_IQR_Excluded"] for r in group),
        "Mean_Incorrect_Touch_Latency_Raw_s":mean(r["Incorrect_Touch_Latency_Raw_s"] for r in group),
        "Mean_Incorrect_Touch_Latency_IQRclean_s":mean(r["Incorrect_Touch_Latency_IQRclean_s"] for r in group),
        "Incorrect_Latency_IQR_Excluded_n":sum(r["Incorrect_Touch_Latency_IQR_Excluded"] for r in group),
        "Mean_Reward_Retrieval_Latency_Raw_s":mean(r["Reward_Retrieval_Latency_Raw_s"] for r in group),
        "Mean_Reward_Retrieval_Latency_IQRclean_s":mean(r["Reward_Retrieval_Latency_IQRclean_s"] for r in group),
        "Reward_Latency_IQR_Excluded_n":sum(r["Reward_Retrieval_Latency_IQR_Excluded"] for r in group),
    })
    return out

def base_fields(r):
    return {k:r.get(k) for k in ["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Probe_Session_Number","Source_Database","SID","Session_DateTime"]}

def make_summaries(trials):
    session_sd=[]; by=defaultdict(list)
    for r in trials: by[(r["Database_Fingerprint"],r["SID"],r["Stimulus_Duration_s"])].append(r)
    for _,g in sorted(by.items(),key=lambda kv:str(kv[0])):
        b=base_fields(g[0]); b["Stimulus_Duration_s"]=g[0]["Stimulus_Duration_s"]; session_sd.append(summarize_group(g,b))

    dec=[]; by=defaultdict(list)
    for r in trials: by[(r["Database_Fingerprint"],r["SID"],r["Session_Progress_Decile"],r["Stimulus_Duration_s"])].append(r)
    for _,g in sorted(by.items(),key=lambda kv:str(kv[0])):
        b=base_fields(g[0]); b["Session_Progress_Decile"]=g[0]["Session_Progress_Decile"]; b["Session_Progress_Percent_Midpoint"]=g[0]["Session_Progress_Percent_Midpoint"]; b["Stimulus_Duration_s"]=g[0]["Stimulus_Duration_s"]; dec.append(summarize_group(g,b))

    # Four-session animal/timepoint averages: average session-level metrics, preserving animal as unit.
    metric_cols=[k for k in session_sd[0].keys() if k not in {"Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Probe_Session_Number","Source_Database","SID","Session_DateTime","Stimulus_Duration_s"}] if session_sd else []
    av=[]; by=defaultdict(list)
    for r in session_sd: by[(r["Project"],r["Animal_ID"],r["Timepoint_Months"],r["Stimulus_Duration_s"])].append(r)
    for _,g in sorted(by.items(),key=lambda kv:str(kv[0])):
        b={k:g[0].get(k) for k in ["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Stimulus_Duration_s"]}
        b["Sessions_Averaged"]=len({x["Probe_Session_Number"] for x in g})
        for c in metric_cols: b[c]=mean(x.get(c) for x in g)
        av.append(b)

    # Next-trial long rows (trial-level outcomes retained for flexible models)
    nxt=[]
    for r in trials:
        if not r["Previous_Outcome_Class"]: continue
        nxt.append({
            **{k:r.get(k) for k in ["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Probe_Session_Number","Source_Database","SID","Trial_Index","Stimulus_Duration_s"]},
            "Image_Presentation_Index":r["Image_Presentation_Index"],
            "Previous_Trial_Index":r["Previous_Trial_Index"],"Previous_Stimulus_Duration_s":r["Previous_Stimulus_Duration_s"],
            "Previous_Image_Presentation_Index":r["Previous_Image_Presentation_Index"],
            "Previous_Trial_Outcome":r["Previous_Trial_Outcome"],"Previous_Outcome_Class":r["Previous_Outcome_Class"],
            "Previous_Trial_Difficulty_Class":r["Previous_Trial_Difficulty_Class"],
            "Previous_Image_Presentation_Difficulty_Class":r["Previous_Image_Presentation_Difficulty_Class"],
            "Previous_Trial_Is_Correction":r["Previous_Trial_Is_Correction"],"Current_Trial_Is_Correction":r["Current_Trial_Is_Correction"],
            "Previous_Response_Latency_Raw_s":r["Previous_Response_Latency_Raw_s"],
            "Previous_Reward_Retrieval_Latency_IQRclean_s":r["Previous_Reward_Retrieval_Latency_IQRclean_s"],
            "Current_Outcome":r["Outcome"],
            "Current_Hit":r["Hit"],"Current_Miss":r["Miss"],"Current_False_Alarm":r["False_Alarm"],"Current_Correct_Rejection":r["Correct_Rejection"],
            "Correct_Touch_Latency_IQRclean_s":r["Correct_Touch_Latency_IQRclean_s"],"Incorrect_Touch_Latency_IQRclean_s":r["Incorrect_Touch_Latency_IQRclean_s"],"Reward_Retrieval_Latency_IQRclean_s":r["Reward_Retrieval_Latency_IQRclean_s"]
        })
    return session_sd,av,dec,nxt



def make_taylor49(trials: list[dict[str,Any]], manifest: list[dict[str,Any]]):
    """Build the exact legacy 49-column Taylor-compatible session summary.

    One row is written per design-eligible QC-approved Probe 2b session.
    Latency values use the same session-level 1.5x IQR-cleaned trial fields as
    the main extractor outputs. AVG_count includes all reconstructed image
    presentations assigned to the stimulus duration, matching the old converter.
    """
    tby=defaultdict(list)
    for r in trials:
        tby[(txt(r.get("Database_Fingerprint")),txt(r.get("SID")))].append(r)
    rows=[]
    for s in sorted([r for r in manifest if txt(r.get("Design_Eligible"))=="YES"],
                    key=lambda r:(txt(r.get("Project_Hint")),txt(r.get("Animal_ID")),parse_dt(r.get("Session_DateTime")) or datetime.min)):
        key=session_key(s); g=tby.get(key,[])
        row={c:"" for c in TAYLOR_49_COLUMNS}
        row.update({
            "AnimalID":txt(s.get("Animal_ID")),
            "Age":s.get("Timepoint_Months", ""),
            "Sex":txt(s.get("Sex")),
            "Treatment":txt(s.get("Treatment")),
            "Genotype":txt(s.get("Genotype")),
            "Strain":txt(s.get("Strain")) or txt(s.get("Genotype")),
            "ExpName":txt(s.get("Project_Hint")),
            "SessionName":txt(s.get("Schedule_Name")),
            "sessionInfoName":txt(s.get("SID")),
            "S_ID":txt(s.get("SID")),
        })
        row["AVG_End Summary - Hits"] = sum(int(r.get("Hit") or 0) for r in g)
        for dur,label in TAYLOR_DURATIONS:
            dg=[r for r in g if r.get("Stimulus_Duration_s") is not None and abs(float(r["Stimulus_Duration_s"])-dur)<0.03]
            if not dg: continue
            row[f"AVG_Average - Correct Choice Latency at {label} SD"] = mean(r.get("Correct_Touch_Latency_IQRclean_s") for r in dg if int(r.get("Hit") or 0))
            row[f"AVG_Average - Mistake Latency at {label} SD"] = mean(r.get("Incorrect_Touch_Latency_IQRclean_s") for r in dg if int(r.get("False_Alarm") or 0))
            row[f"AVG_Average - Reward Retrieval Latency at {label} SD"] = mean(r.get("Reward_Retrieval_Latency_IQRclean_s") for r in dg if int(r.get("Hit") or 0))
            row[f"AVG_count at {label}"] = len(dg)
            row[f"AVG_End Summary - CorrectRejection at {label} SD"] = sum(int(r.get("Correct_Rejection") or 0) for r in dg)
            row[f"AVG_End Summary - Hits at {label} SD"] = sum(int(r.get("Hit") or 0) for r in dg)
            row[f"AVG_End Summary - Miss at {label} SD"] = sum(int(r.get("Miss") or 0) for r in dg)
            row[f"AVG_End Summary - Mistake at {label} SD"] = sum(int(r.get("False_Alarm") or 0) for r in dg)
        rows.append(row)
    return rows


def make_legacy67(trials: list[dict[str,Any]], manifest: list[dict[str,Any]]):
    """Build the exact legacy 67-column extended CPT session summary."""
    base_rows=make_taylor49(trials, manifest)
    eligible=sorted([r for r in manifest if txt(r.get("Design_Eligible"))=="YES"],
                    key=lambda r:(txt(r.get("Project_Hint")),txt(r.get("Animal_ID")),parse_dt(r.get("Session_DateTime")) or datetime.min))
    tby=defaultdict(list)
    for r in trials:
        tby[(txt(r.get("Database_Fingerprint")),txt(r.get("SID")))].append(r)
    out=[]
    for s,base in zip(eligible,base_rows):
        row={c:"" for c in LEGACY_67_COLUMNS}
        row.update(base)
        row["Date_Time"]=txt(s.get("Session_DateTime"))
        row["chronological day"]=s.get("Probe_Session_Number","")
        g=tby.get(session_key(s),[])
        for dur,label in TAYLOR_DURATIONS:
            dg=[r for r in g if r.get("Stimulus_Duration_s") is not None and abs(float(r["Stimulus_Duration_s"])-dur)<0.03]
            h=sum(int(r.get("Hit") or 0) for r in dg)
            m=sum(int(r.get("Miss") or 0) for r in dg)
            fa=sum(int(r.get("False_Alarm") or 0) for r in dg)
            cr=sum(int(r.get("Correct_Rejection") or 0) for r in dg)
            met=rate_metrics(h,m,fa,cr)
            row[f"Hit Rate at {label} SD"]=met["Hit_Rate"] if met["Hit_Rate"] is not None else ""
            row[f"False Alarm Rate at {label} SD"]=met["False_Alarm_Rate"] if met["False_Alarm_Rate"] is not None else ""
            row[f"dPrime at {label} SD"]=met["d_prime"] if met["d_prime"] is not None else ""
            row[f"c Response Bias at {label} SD"]=met["criterion_c"] if met["criterion_c"] is not None else ""
        out.append(row)
    return out


def make_legacy67_by_iti(trials: list[dict[str,Any]], manifest: list[dict[str,Any]]):
    """Build a 67-style session summary split into separate 2s and 3s ITI rows.

    The original CPT_67 file stays as the mixed-ITI compatibility export. This
    companion file adds Current_ITI_s and writes up to two rows per session, so
    downstream graphing can compare 2s vs 3s ITI without re-summarizing trials.
    """
    eligible=sorted([r for r in manifest if txt(r.get("Design_Eligible"))=="YES"],
                    key=lambda r:(txt(r.get("Project_Hint")),txt(r.get("Animal_ID")),parse_dt(r.get("Session_DateTime")) or datetime.min))
    tby=defaultdict(list)
    for r in trials:
        tby[(txt(r.get("Database_Fingerprint")),txt(r.get("SID")))].append(r)
    out=[]
    for s in eligible:
        g=tby.get(session_key(s),[])
        for iti in (2,3):
            ig=[
                r for r in g
                if num(r.get("Current_ITI_s")) is not None
                and abs(float(r.get("Current_ITI_s"))-iti)<0.03
            ]
            if not ig:
                continue
            row={c:"" for c in LEGACY_67_BY_ITI_COLUMNS}
            row.update({
                "AnimalID":txt(s.get("Animal_ID")),
                "Age":s.get("Timepoint_Months", ""),
                "Sex":txt(s.get("Sex")),
                "Treatment":txt(s.get("Treatment")),
                "Genotype":txt(s.get("Genotype")),
                "Strain":txt(s.get("Strain")) or txt(s.get("Genotype")),
                "ExpName":txt(s.get("Project_Hint")),
                "SessionName":txt(s.get("Schedule_Name")),
                "sessionInfoName":txt(s.get("SID")),
                "S_ID":txt(s.get("SID")),
                "Date_Time":txt(s.get("Session_DateTime")),
                "chronological day":s.get("Probe_Session_Number",""),
                "Current_ITI_s":iti,
                "AVG_End Summary - Hits":sum(int(r.get("Hit") or 0) for r in ig),
            })
            for dur,label in TAYLOR_DURATIONS:
                dg=[
                    r for r in ig
                    if r.get("Stimulus_Duration_s") is not None
                    and abs(float(r["Stimulus_Duration_s"])-dur)<0.03
                ]
                if not dg:
                    continue
                row[f"AVG_Average - Correct Choice Latency at {label} SD"] = mean(r.get("Correct_Touch_Latency_IQRclean_s") for r in dg if int(r.get("Hit") or 0))
                row[f"AVG_Average - Mistake Latency at {label} SD"] = mean(r.get("Incorrect_Touch_Latency_IQRclean_s") for r in dg if int(r.get("False_Alarm") or 0))
                row[f"AVG_Average - Reward Retrieval Latency at {label} SD"] = mean(r.get("Reward_Retrieval_Latency_IQRclean_s") for r in dg if int(r.get("Hit") or 0))
                row[f"AVG_count at {label}"] = len(dg)
                row[f"AVG_End Summary - CorrectRejection at {label} SD"] = sum(int(r.get("Correct_Rejection") or 0) for r in dg)
                row[f"AVG_End Summary - Hits at {label} SD"] = sum(int(r.get("Hit") or 0) for r in dg)
                row[f"AVG_End Summary - Miss at {label} SD"] = sum(int(r.get("Miss") or 0) for r in dg)
                row[f"AVG_End Summary - Mistake at {label} SD"] = sum(int(r.get("False_Alarm") or 0) for r in dg)
                h=sum(int(r.get("Hit") or 0) for r in dg)
                m=sum(int(r.get("Miss") or 0) for r in dg)
                fa=sum(int(r.get("False_Alarm") or 0) for r in dg)
                cr=sum(int(r.get("Correct_Rejection") or 0) for r in dg)
                met=rate_metrics(h,m,fa,cr)
                row[f"Hit Rate at {label} SD"]=met["Hit_Rate"] if met["Hit_Rate"] is not None else ""
                row[f"False Alarm Rate at {label} SD"]=met["False_Alarm_Rate"] if met["False_Alarm_Rate"] is not None else ""
                row[f"dPrime at {label} SD"]=met["d_prime"] if met["d_prime"] is not None else ""
                row[f"c Response Bias at {label} SD"]=met["criterion_c"] if met["criterion_c"] is not None else ""
            out.append(row)
    return out


def make_legacy49_by_iti(legacy67_by_iti):
    """49 legacy fields plus ITI; one record per session/condition."""
    return [{**{k: r.get(k, "") for k in TAYLOR_49_COLUMNS},
             "Current_ITI_s": r.get("Current_ITI_s", "")} for r in legacy67_by_iti]


def make_stage4_legacy_exports(trials, manifest):
    """Create stage 4 legacy exports with the same column conventions as Probe 2b.

    Stage 4 runs at fixed 2s SD. Unsupported durations stay blank.
    """
    sessions = []
    for row in manifest:
        r = row.copy()
        r["Design_Eligible"] = "YES"
        r["Probe_Session_Number"] = row.get("Baseline_Day_Number", "")
        sessions.append(r)
    t49 = make_taylor49(trials, sessions)
    t67 = make_legacy67(trials, sessions)
    t67iti = make_legacy67_by_iti(trials, sessions)
    return t49, t67, make_legacy49_by_iti(t67iti), t67iti

# ----------------------------- main --------------------------------
def run(atlas_dir: Path, output_dir: Path | None=None, session_selection_path: Path | None=None):
    reports=atlas_dir/"reports" if (atlas_dir/"reports").exists() else atlas_dir
    master_candidates=[
        reports/"ATLAS_SESSION_MASTER_FINAL.csv",
        atlas_dir/"ATLAS_SESSION_MASTER_FINAL.csv",
        reports/"ATLAS_SESSION_MASTER.csv",
        atlas_dir/"ATLAS_SESSION_MASTER.csv",
    ]
    master=next((p for p in master_candidates if p.exists()), None)
    if not master:
        searched="\n".join(str(p) for p in master_candidates)
        raise FileNotFoundError(f"Could not find ATLAS_SESSION_MASTER_FINAL.csv or ATLAS_SESSION_MASTER.csv. Searched:\n{searched}")
    db=find_index_db(atlas_dir)
    if not db: raise FileNotFoundError("Could not find cache/NMR_ABET_Atlas.sqlite under the selected Atlas folder")
    out=output_dir or (atlas_dir/"probe2b_analysis")
    out.mkdir(parents=True,exist_ok=True)

    master_rows=read_csv(master)
    metadata_path=find_metadata_csv(reports) or find_metadata_csv(atlas_dir)
    if not metadata_path:
        raise FileNotFoundError(
            f"Could not find ATLAS_ANIMAL_METADATA.csv beside {master}. "
            "Run Atlas/QC first, then rerun this extractor."
        )
    metadata_rows=read_csv(metadata_path)
    master_rows, metadata_matched, metadata_unmatched = merge_animal_metadata(master_rows, metadata_rows)

    reconciliation_path = find_reconciliation_workbook(atlas_dir, reports)
    reconciliation_rows = []
    reconciliation_audit = []
    reconciliation_counts = {}
    if reconciliation_path:
        reconciliation_rows = read_decision_workbook(reconciliation_path)
        master_rows, reconciliation_audit, reconciliation_counts = apply_reconciliation_decisions(master_rows, reconciliation_rows)
        write_csv(out/"ATLAS_RECONCILIATION_DECISIONS_APPLIED.csv", reconciliation_audit)
    else:
        write_csv(out/"ATLAS_RECONCILIATION_DECISIONS_APPLIED.csv", [])

    # Finalized ATLAS_ANIMAL_METADATA is the approved animal population. Sessions
    # for animals absent from that table remain in Atlas for audit, but do not
    # enter Probe 2b / Stage 4 analysis exports.
    selection_path=session_selection_path or find_selection_csv(reports) or find_selection_csv(atlas_dir)
    raw_selection_rows=read_table(selection_path) if selection_path else []

    analysis_master_rows=[
        r for r in master_rows
        if txt(r.get("Metadata_Match_Status")) in {"MATCHED", "MATCHED_BY_RECONCILIATION"}
        and txt(r.get("Reconciliation_Include") or "YES") == "YES"
    ]
    selection_rows=[]
    source_selection_audit=[]
    if raw_selection_rows:
        selection_rows, source_selection_audit = map_source_selection_to_atlas(
            raw_selection_rows,
            analysis_master_rows,
            default_project="Lecanemab" if "lecanemab" in selection_path.name.lower() else "",
        )
        write_csv(out/"PROBE2B_SOURCE_SESSION_SELECTION_AUDIT.csv", source_selection_audit)
        missing_template_rows = [
            r for r in source_selection_audit
            if r.get("Atlas_Master_Match") == "MISSING_IN_ATLAS_MASTER"
        ]
        if missing_template_rows:
            raise RuntimeError(
                "Some rows in the supplied session-selection/template file did not match Atlas sessions. "
                "Check PROBE2B_SOURCE_SESSION_SELECTION_AUDIT.csv, then correct the template or rerun Atlas/QC if the "
                "problem is animal ID or session inclusion."
            )
    if selection_rows and any(txt(r.get("Project_Group") or r.get("Project_Hint") or r.get("Project")).casefold()=="lecanemab" for r in selection_rows):
        # Corrected Sheet2 S_ID values are not Atlas session IDs. The mapped
        # whitelist must carry the Atlas database fingerprint and SID. Refuse
        # the older unmapped file rather than silently matching coincidental
        # numeric IDs.
        required = {"Atlas_Master_SID", "Atlas_Master_Database_Fingerprint"}
        missing = sorted(required - set(selection_rows[0].keys()))
        if missing:
            raise RuntimeError(
                "The session-selection file could not be mapped to Atlas session IDs. "
                "Check PROBE2B_SOURCE_SESSION_SELECTION_AUDIT.csv for missing rows. "
                "A mapped whitelist must contain Atlas_Master_SID and "
                "Atlas_Master_Database_Fingerprint."
            )
    if selection_rows:
        master_probe_keys = defaultdict(int)
        for row in analysis_master_rows:
            if txt(row.get("Session_Type_Hint")).lower() == "probe 2b":
                master_probe_keys[selection_key(row)] += 1
        selection_audit=[]
        for row in selection_rows:
            key=selection_key(row)
            audit=row.copy()
            audit["Atlas_Master_Match"]="MATCHED" if master_probe_keys.get(key,0) else "MISSING_IN_ATLAS_MASTER"
            audit["Atlas_Master_Match_Count"]=str(master_probe_keys.get(key,0))
            selection_audit.append(audit)
        write_csv(out/"PROBE2B_SESSION_SELECTION_AUDIT.csv",selection_audit)
    manifest,qc=build_manifest(analysis_master_rows, selection_rows)
    timepoint_detail=make_timepoint_assignment_detail(manifest)
    write_csv(out/"PROBE2B_SESSION_MANIFEST.csv",manifest)
    write_csv(out/"PROBE2B_TIMEPOINT_ASSIGNMENT_QC.csv",qc)
    write_csv(out/"PROBE2B_TIMEPOINT_ASSIGNMENT_DETAIL.csv",timepoint_detail)
    session_review_rows = make_probe_session_selection_review_rows(manifest)
    session_review_path = out / "PROBE2B_SESSION_SELECTION_REVIEW.xlsx"
    if session_review_rows:
        write_probe_session_selection_review_workbook(session_review_path, session_review_rows)
    eligible=[r for r in manifest if txt(r.get("Design_Eligible"))=="YES"]
    if not eligible:
        raise RuntimeError(
            "No eligible Probe 2b sessions after QC/design rules. "
            "Review PROBE2B_SESSION_SELECTION_REVIEW.xlsx if it exists, otherwise check "
            "PROBE2B_SESSION_MANIFEST.csv and PROBE2B_TIMEPOINT_ASSIGNMENT_QC.csv."
        )
    keys={session_key(r) for r in eligible}
    raw=fetch_trials(db,keys)
    trials=enrich_trials(raw,eligible)
    if not trials: raise RuntimeError("No matching trial rows were found for the eligible Probe 2b sessions. Check Atlas cache and final master paths.")
    write_csv(out/"PROBE2B_TRIAL_MASTER.csv",trials)
    session_sd,av,dec,nxt=make_summaries(trials)
    write_csv(out/"PROBE2B_SESSION_SD_METRICS.csv",session_sd)
    write_csv(out/"PROBE2B_TIMEPOINT_AVERAGES.csv",av)
    write_csv(out/"PROBE2B_WITHIN_SESSION_DECILES.csv",dec)
    write_csv(out/"PROBE2B_NEXT_TRIAL.csv",nxt)
    taylor49=make_taylor49(trials,eligible)
    taylor49=normalize_legacy_numeric_cells(taylor49,TAYLOR_49_COLUMNS)
    write_csv(out/"CPT_49_COLUMN_ALL_DATABASES.csv",taylor49,TAYLOR_49_COLUMNS)
    legacy67=make_legacy67(trials,eligible)
    legacy67=normalize_legacy_numeric_cells(legacy67,LEGACY_67_COLUMNS)
    write_csv(out/"CPT_67_COLUMN_ALL_DATABASES.csv",legacy67,LEGACY_67_COLUMNS)
    legacy67_by_iti=make_legacy67_by_iti(trials,eligible)
    legacy67_by_iti=normalize_legacy_numeric_cells(legacy67_by_iti,LEGACY_67_BY_ITI_COLUMNS)
    write_csv(out/"CPT_67_COLUMN_ALL_DATABASES_BY_ITI.csv",legacy67_by_iti,LEGACY_67_BY_ITI_COLUMNS)
    write_csv(out/"CPT_49_COLUMN_ALL_DATABASES_BY_ITI.csv",make_legacy49_by_iti(legacy67_by_iti),TAYLOR_49_COLUMNS+["Current_ITI_s"])

    # Optional matched Stage 4 baseline layer. Missing/partial Stage 4 never excludes Probe 2b.
    stage4_manifest,stage4_qc=build_stage4_manifest(analysis_master_rows,manifest)
    write_csv(out/"STAGE4_BASELINE_SESSION_MANIFEST.csv",stage4_manifest)
    write_csv(out/"STAGE4_BASELINE_QC.csv",stage4_qc)
    stage4_trials=[]; stage4_session=[]; stage4_avg=[]; baseline_probe=[]
    if stage4_manifest:
        stage4_keys={session_key(r) for r in stage4_manifest}
        stage4_raw=fetch_trials(db,stage4_keys)
        stage4_trials=enrich_stage4_trials(stage4_raw,stage4_manifest)
        write_csv(out/"STAGE4_BASELINE_TRIAL_MASTER.csv",stage4_trials)
        stage4_session,stage4_avg=make_stage4_summaries(stage4_trials)
        write_csv(out/"STAGE4_BASELINE_SESSION_METRICS.csv",stage4_session)
        write_csv(out/"STAGE4_BASELINE_TIMEPOINT_AVERAGES.csv",stage4_avg)
        stage4_by_iti, stage4_by_iti_avg, stage4_deciles_by_iti, stage4_iti_qc = make_stage4_iti_summaries(stage4_trials)
        write_csv(out/"STAGE4_BASELINE_SESSION_METRICS_BY_ITI.csv", stage4_by_iti)
        write_csv(out/"STAGE4_BASELINE_TIMEPOINT_AVERAGES_BY_ITI.csv", stage4_by_iti_avg)
        write_csv(out/"STAGE4_BASELINE_WITHIN_SESSION_DECILES_BY_ITI.csv", stage4_deciles_by_iti)
        write_csv(out/"STAGE4_BASELINE_ITI_QC.csv", stage4_iti_qc)
        s49, s67, s49iti, s67iti = make_stage4_legacy_exports(stage4_trials,stage4_manifest)
        write_csv(out/"STAGE4_CPT_49_COLUMN_ALL_DATABASES.csv",s49,TAYLOR_49_COLUMNS)
        write_csv(out/"STAGE4_CPT_67_COLUMN_ALL_DATABASES.csv",s67,LEGACY_67_COLUMNS)
        write_csv(out/"STAGE4_CPT_49_COLUMN_ALL_DATABASES_BY_ITI.csv",s49iti,TAYLOR_49_COLUMNS+["Current_ITI_s"])
        write_csv(out/"STAGE4_CPT_67_COLUMN_ALL_DATABASES_BY_ITI.csv",s67iti,LEGACY_67_BY_ITI_COLUMNS)
        baseline_probe=make_baseline_probe_2s(stage4_avg,av)
        write_csv(out/"BASELINE_TO_PROBE_2S_LONG.csv",baseline_probe)
    else:
        write_csv(out/"STAGE4_BASELINE_TRIAL_MASTER.csv",[])
        write_csv(out/"STAGE4_BASELINE_SESSION_METRICS.csv",[])
        write_csv(out/"STAGE4_BASELINE_TIMEPOINT_AVERAGES.csv",[])
        for name in ["STAGE4_BASELINE_SESSION_METRICS_BY_ITI.csv", "STAGE4_BASELINE_TIMEPOINT_AVERAGES_BY_ITI.csv", "STAGE4_BASELINE_WITHIN_SESSION_DECILES_BY_ITI.csv", "STAGE4_BASELINE_ITI_QC.csv"]:
            write_csv(out/name, [])
        write_csv(out/"BASELINE_TO_PROBE_2S_LONG.csv",[])
        for name,columns in [
            ("STAGE4_CPT_49_COLUMN_ALL_DATABASES.csv",TAYLOR_49_COLUMNS),
            ("STAGE4_CPT_67_COLUMN_ALL_DATABASES.csv",LEGACY_67_COLUMNS),
            ("STAGE4_CPT_49_COLUMN_ALL_DATABASES_BY_ITI.csv",TAYLOR_49_COLUMNS+["Current_ITI_s"]),
            ("STAGE4_CPT_67_COLUMN_ALL_DATABASES_BY_ITI.csv",LEGACY_67_BY_ITI_COLUMNS)]:
            write_csv(out/name,[],columns)

    sessions_expected=len(keys); sessions_found=len({(r["Database_Fingerprint"],r["SID"]) for r in trials})
    summary=[
        {"Item":"Atlas final master","Value":str(master)},
        {"Item":"Atlas trial cache","Value":str(db)},
        {"Item":"Atlas animal metadata","Value":str(metadata_path)},
        {"Item":"Atlas reconciliation decision workbook","Value":str(reconciliation_path) if reconciliation_path else "NOT FOUND — metadata-only filtering used"},
        {"Item":"Reconciliation decision rows read","Value":len(reconciliation_rows)},
        {"Item":"Reconciliation audit rows written","Value":len(reconciliation_audit)},
        {"Item":"Reconciliation KEEP session rows","Value":reconciliation_counts.get("KEEP", 0)},
        {"Item":"Reconciliation EXCLUDE session rows","Value":reconciliation_counts.get("EXCLUDE", 0)},
        {"Item":"Reconciliation REMAP session rows","Value":reconciliation_counts.get("REMAP", 0)},
        {"Item":"Reconciliation unresolved session rows excluded","Value":reconciliation_counts.get("UNRESOLVED", 0) + reconciliation_counts.get("REMAP_MISSING_CORRECT_ID", 0)},
        {"Item":"Requested Probe 2b session-selection file","Value":str(selection_path) if selection_path else "NOT FOUND — automatic session selection used"},
        {"Item":"Requested session-selection rows read","Value":len(raw_selection_rows)},
        {"Item":"Requested session-selection rows mapped to Atlas","Value":len(selection_rows)},
        {"Item":"Requested session-selection rows missing from Atlas","Value":sum(1 for r in source_selection_audit if r.get("Atlas_Master_Match")=="MISSING_IN_ATLAS_MASTER")},
        {"Item":"Session-master rows matched to Project + Animal ID metadata","Value":metadata_matched},
        {"Item":"Session-master rows unmatched to Project + Animal ID metadata (retained in Atlas, excluded from analysis exports)","Value":metadata_unmatched},
        {"Item":"Approved Project + Animal combinations in finalized metadata","Value":len({(txt(r.get("Project_Group") or r.get("Project_Hint")),txt(r.get("AnimalID") or r.get("Animal_ID"))) for r in metadata_rows if txt(r.get("AnimalID") or r.get("Animal_ID"))})},
        {"Item":"Probe sessions in QC-approved manifest","Value":len(manifest)},
        {"Item":"Probe animal/timepoint blocks in detailed QC","Value":len(timepoint_detail)},
        {"Item":"Probe animal/timepoint blocks needing detailed QC review","Value":sum(1 for r in timepoint_detail if txt(r.get("QC_Status"))=="CHECK")},
        {"Item":"Probe session-choice review rows needing USE/EXCLUDE decisions","Value":len(session_review_rows)},
        {"Item":"Probe session-choice review workbook","Value":str(session_review_path) if session_review_rows else "Not needed — no >4-session Probe 2b blocks detected"},
        {"Item":"Probe sessions eligible after design rules","Value":sessions_expected},
        {"Item":"Eligible sessions with cached trial data","Value":sessions_found},
        {"Item":"Extracted trial rows","Value":len(trials)},
        {"Item":"Session × stimulus-duration rows","Value":len(session_sd)},
        {"Item":"Animal × timepoint × stimulus-duration average rows","Value":len(av)},
        {"Item":"Within-session decile rows","Value":len(dec)},
        {"Item":"Next-trial rows","Value":len(nxt)},
        {"Item":"Taylor-compatible 49-column session rows","Value":len(taylor49)},
        {"Item":"Legacy extended 67-column session rows","Value":len(legacy67)},
        {"Item":"ITI-split 67-column session rows","Value":len(legacy67_by_iti)},
        {"Item":"Matched Stage 4 baseline sessions selected","Value":len(stage4_manifest)},
        {"Item":"Matched Stage 4 trial rows","Value":len(stage4_trials)},
        {"Item":"Animal × timepoint Stage 4 baseline averages","Value":len(stage4_avg)},
        {"Item":"Baseline-to-Probe 2s long rows","Value":len(baseline_probe)},
        {"Item":"Timepoints with full 4-session Stage 4 baseline","Value":sum(1 for r in stage4_qc if r.get("Baseline_Status")=="FULL_4")},
        {"Item":"Timepoints with partial/missing Stage 4 baseline","Value":sum(1 for r in stage4_qc if r.get("Baseline_Status")!="FULL_4")},
    ]
    write_csv(out/"PROBE2B_EXTRACTION_SUMMARY.csv",summary,["Item","Value"])
    return {"output":out,"summary":summary,"sessions_expected":sessions_expected,"sessions_found":sessions_found,"trials":len(trials)}

def gui():
    import tkinter as tk
    from tkinter import filedialog,messagebox,ttk
    root=tk.Tk(); root.title("Atlas Dual Phase Extractor"); root.geometry("800x560")
    frm=ttk.Frame(root,padding=14); frm.pack(fill="both",expand=True)
    atlas=tk.StringVar(); out=tk.StringVar(); selection=tk.StringVar()
    ttk.Label(frm,text="NMR ABET Atlas — Dual Phase Extractor",font=("Segoe UI",18,"bold")).grid(row=0,column=0,columnspan=3,sticky="w")
    ttk.Label(frm,text="Uses the QC-final Probe session master + Atlas trial cache. Optional: provide an Arash/source-of-truth CSV/XLSX or PROBE2B_SESSION_SELECTION_REVIEW.xlsx to choose exact sessions.").grid(row=1,column=0,columnspan=3,sticky="w",pady=(0,14))
    def bd(var):
        p=filedialog.askdirectory();
        if p: var.set(p)
    def bf(var):
        p=filedialog.askopenfilename(
            title="Choose source-of-truth or Probe 2b session-review CSV/XLSX",
            filetypes=[("CSV or Excel", "*.csv *.xlsx *.xlsm"), ("All files", "*.*")]
        )
        if p: var.set(p)
    for row,label,var in [(2,"Atlas output folder",atlas),(3,"Output folder (optional)",out)]:
        ttk.Label(frm,text=label).grid(row=row,column=0,sticky="w",pady=5)
        ttk.Entry(frm,textvariable=var,width=70).grid(row=row,column=1,sticky="ew",padx=8)
        ttk.Button(frm,text="Browse…",command=lambda v=var:bd(v)).grid(row=row,column=2)
    ttk.Label(frm,text="Session selection/review CSV/XLSX (optional)").grid(row=4,column=0,sticky="w",pady=5)
    ttk.Entry(frm,textvariable=selection,width=70).grid(row=4,column=1,sticky="ew",padx=8)
    ttk.Button(frm,text="Browse…",command=lambda:bf(selection)).grid(row=4,column=2)
    text=tk.Text(frm,height=20,wrap="word",font=("Consolas",9)); text.grid(row=5,column=0,columnspan=3,sticky="nsew",pady=(12,0))
    frm.columnconfigure(1,weight=1); frm.rowconfigure(5,weight=1)
    def go():
        if not atlas.get(): messagebox.showerror("Missing Atlas folder","Choose the Atlas output folder."); return
        text.delete("1.0","end")
        try:
            text.insert("end","Reading QC-approved Probe sessions, Atlas trial cache, and matched Stage 4 baselines…\n"); root.update_idletasks()
            res=run(
                Path(atlas.get()),
                Path(out.get()) if out.get() else None,
                Path(selection.get()) if selection.get() else None,
            )
            for x in res["summary"]: text.insert("end",f"{x['Item']}: {x['Value']}\n")
            text.insert("end",f"\nDONE\nOutputs: {res['output']}\n")
            messagebox.showinfo("Probe 2b extraction complete",f"Done.\n\nSessions matched: {res['sessions_found']}/{res['sessions_expected']}\nTrials: {res['trials']:,}\n\nOutputs:\n{res['output']}")
        except Exception as e:
            text.insert("end","\n"+traceback.format_exc()); messagebox.showerror("Extractor error",str(e))
    ttk.Button(frm,text="EXTRACT DUAL PHASE: PROBE 2B + STAGE 4",command=go).grid(row=6,column=0,columnspan=3,sticky="ew",pady=(10,0),ipady=7)
    root.mainloop()

def main():
    p=argparse.ArgumentParser(description="Extract QC-approved Probe 2b trials, CPT metrics, and matched Stage 4 baselines from NMR ABET Atlas")
    p.add_argument("--atlas",help="Atlas output folder containing reports/ and cache/")
    p.add_argument("--output",help="Optional output folder")
    p.add_argument("--session-selection",help="Optional CSV/XLSX with AnimalID and specific sessions to extract, including PROBE2B_SESSION_SELECTION_REVIEW.xlsx")
    a=p.parse_args()
    if a.atlas:
        r=run(
            Path(a.atlas),
            Path(a.output) if a.output else None,
            Path(a.session_selection) if a.session_selection else None,
        )
        print("DONE",r["output"]); return 0
    gui(); return 0

if __name__=="__main__":
    raise SystemExit(main())
