from __future__ import annotations

import sys
import math
import json
import traceback
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import norm, chi2

try:
    import statsmodels.formula.api as smf
    import statsmodels.api as sm
    from patsy import build_design_matrices
except Exception:
    smf = None
    sm = None
    build_design_matrices = None

# -----------------------------
# Configuration
# -----------------------------
IQR_MULTIPLIER = 3.0
MIN_IQR_N = 8
FIRST_N_PROBE_SESSIONS = 4
OUTPUT_FOLDER_NAME = "ATLAS_ANALYSIS_OUTPUT"

RAW_LATENCY_COLS = {
    "Correct": "Correct_Touch_Latency_Raw_s",
    "Incorrect": "Incorrect_Touch_Latency_Raw_s",
    "Reward": "Reward_Retrieval_Latency_Raw_s",
}
CORE_COLS = ["Hit", "Miss", "False_Alarm", "Correct_Rejection"]
META_COLS = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment", "Timepoint_Months", "Timepoint_Label"]


def read_table(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path)
    if ext == ".csv":
        return pd.read_csv(path, low_memory=False)
    if ext in (".parquet", ".pq"):
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input format: {path}")


def find_input(folder: Path, stem: str) -> Path | None:
    candidates = []
    for ext in [".csv", ".xlsx", ".xlsm", ".xls", ".parquet"]:
        p = folder / f"{stem}{ext}"
        if p.exists():
            candidates.append(p)
    if candidates:
        # Prefer CSV/Parquet for very large files, then XLSX.
        pref = {".parquet": 0, ".pq": 0, ".csv": 1, ".xlsx": 2, ".xlsm": 3, ".xls": 4}
        return sorted(candidates, key=lambda p: pref.get(p.suffix.lower(), 9))[0]

    # Allow suffixes such as (1), _FULL, etc.
    loose = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in (".csv", ".xlsx", ".xlsm", ".xls", ".parquet", ".pq"):
            if stem.lower() in p.stem.lower():
                loose.append(p)
    if not loose:
        return None
    pref = {".parquet": 0, ".pq": 0, ".csv": 1, ".xlsx": 2, ".xlsm": 3, ".xls": 4}
    return sorted(loose, key=lambda p: (pref.get(p.suffix.lower(), 9), len(p.name)))[0]


def clean_common(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment", "Timepoint_Label", "Schedule_Name", "Outcome", "Previous_Outcome_Class"]:
        if c in df.columns:
            df[c] = df[c].where(df[c].isna(), df[c].astype(str).str.strip())
    for c in ["Timepoint_Months", "Probe_Session_Number", "Stimulus_Duration_s", "Trial_Index", "SID", "Baseline_Day_Number"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in CORE_COLS + ["Correction_Trial_Correct_Rejection", "Correction_Trial_Mistake"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in RAW_LATENCY_COLS.values():
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# -----------------------------
# Metadata treatment validation
# -----------------------------
ALLOWED_TREATMENTS = {
    "lecanemab": {"PBS", "Lecanemab"},
    "vaccine": {"Sham", "Vaccine"},
}

# Explicit reconciliations approved by the experiment team.
# Keyed by (project_lower, Animal_ID) so shared IDs across projects remain distinct animals.
APPROVED_TREATMENT_OVERRIDES = {
    ("lecanemab", "AS204M3"): "PBS",
}


def normalize_and_validate_treatments(df: pd.DataFrame, source_name: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalize project/treatment labels conservatively, apply only approved animal-specific
    reconciliations, and stop analysis if any unexpected treatment category remains.

    Returns
    -------
    cleaned_df, audit_df
    """
    df = df.copy()
    audit_rows = []

    required = {"Project", "Animal_ID", "Treatment"}
    if not required.issubset(df.columns):
        missing = sorted(required - set(df.columns))
        raise ValueError(f"Cannot validate treatment metadata; missing columns: {missing}")

    # Canonicalize known project names without guessing unknown projects.
    project_map = {"lecanemab": "Lecanemab", "vaccine": "Vaccine"}

    for idx in df.index:
        raw_project = df.at[idx, "Project"]
        raw_animal = df.at[idx, "Animal_ID"]
        raw_treat = df.at[idx, "Treatment"]

        proj_txt = "" if pd.isna(raw_project) else str(raw_project).strip()
        animal_txt = "" if pd.isna(raw_animal) else str(raw_animal).strip()
        treat_txt = "" if pd.isna(raw_treat) else str(raw_treat).strip()

        proj_key = proj_txt.lower()
        if proj_key in project_map:
            df.at[idx, "Project"] = project_map[proj_key]

        # Normalize exact case variants of allowed labels only.
        allowed = ALLOWED_TREATMENTS.get(proj_key)
        if allowed:
            canon_lookup = {x.lower(): x for x in allowed}
            if treat_txt.lower() in canon_lookup:
                canonical = canon_lookup[treat_txt.lower()]
                if canonical != treat_txt:
                    audit_rows.append({
                        "Source": source_name,
                        "Project": project_map.get(proj_key, proj_txt),
                        "Animal_ID": animal_txt,
                        "Original_Treatment": treat_txt,
                        "Final_Treatment": canonical,
                        "Action": "NORMALIZED_CASE_OR_WHITESPACE",
                        "Reason": "Matched an allowed project-specific treatment label"
                    })
                df.at[idx, "Treatment"] = canonical
                treat_txt = canonical

        # Apply only explicitly approved reconciliation decisions.
        override = APPROVED_TREATMENT_OVERRIDES.get((proj_key, animal_txt))
        if override is not None and treat_txt != override:
            audit_rows.append({
                "Source": source_name,
                "Project": project_map.get(proj_key, proj_txt),
                "Animal_ID": animal_txt,
                "Original_Treatment": treat_txt,
                "Final_Treatment": override,
                "Action": "APPROVED_RECONCILIATION_OVERRIDE",
                "Reason": "Experiment-team reconciliation decision"
            })
            df.at[idx, "Treatment"] = override

    # Validate allowed levels after approved corrections.
    bad_rows = []
    for project, dp in df.groupby("Project", dropna=False):
        ptxt = "" if pd.isna(project) else str(project).strip()
        pkey = ptxt.lower()
        allowed = ALLOWED_TREATMENTS.get(pkey)
        if allowed is None:
            continue
        bad = dp.loc[~dp["Treatment"].isin(allowed), ["Animal_ID", "Treatment"]].drop_duplicates()
        for _, row in bad.iterrows():
            bad_rows.append({
                "Source": source_name,
                "Project": ptxt,
                "Animal_ID": row["Animal_ID"],
                "Original_Treatment": row["Treatment"],
                "Final_Treatment": row["Treatment"],
                "Action": "ERROR_UNEXPECTED_TREATMENT",
                "Reason": f"Allowed labels for {ptxt}: {sorted(allowed)}"
            })

    audit = pd.DataFrame(audit_rows + bad_rows)

    if bad_rows:
        preview = "; ".join(
            f"{r['Project']} / {r['Animal_ID']} / {r['Original_Treatment']}"
            for r in bad_rows[:20]
        )
        raise ValueError(
            "Unexpected treatment metadata detected. Analysis stopped before QC/statistics. "
            f"Examples: {preview}. Allowed labels: "
            "Lecanemab={PBS, Lecanemab}; Vaccine={Sham, Vaccine}."
        )

    return df, audit


def apply_analysis_eligibility(df: pd.DataFrame, is_probe: bool) -> pd.DataFrame:
    df = df.copy()
    eligible = pd.Series(True, index=df.index)
    reason = pd.Series("ELIGIBLE", index=df.index, dtype="object")

    if is_probe and "Probe_Session_Number" in df.columns:
        bad = df["Probe_Session_Number"].notna() & (df["Probe_Session_Number"] > FIRST_N_PROBE_SESSIONS)
        eligible.loc[bad] = False
        reason.loc[bad] = f"PROBE_SESSION_GT_{FIRST_N_PROBE_SESSIONS}"

    # Study-specific rule supplied by the experiment team:
    # Lecanemab Cohort 1 is eligible at 6 and 9 months, not for 12-month treatment analysis.
    needed = {"Project", "Cohort", "Timepoint_Months"}
    if needed.issubset(df.columns):
        proj = df["Project"].astype(str).str.lower()
        cohort = df["Cohort"].astype(str).str.lower().str.replace(" ", "", regex=False)
        tp = pd.to_numeric(df["Timepoint_Months"], errors="coerce")
        c1_12 = proj.eq("lecanemab") & cohort.isin(["cohort1", "1", "1.0"]) & tp.eq(12)
        eligible.loc[c1_12] = False
        reason.loc[c1_12] = "LECANEMAB_COHORT1_12M_INELIGIBLE"

    df["Analysis_Eligible"] = eligible
    df["Analysis_Eligibility_Reason"] = reason
    return df


def add_core_trial_flag(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    present = [c for c in CORE_COLS if c in df.columns]
    if len(present) != 4:
        raise ValueError(f"Missing one or more core outcome columns. Required: {CORE_COLS}")
    ncore = df[CORE_COLS].fillna(0).sum(axis=1)
    df["Core_Trial"] = ncore.eq(1)
    df["Core_Trial_Flag_Sum"] = ncore
    return df


def _iqr_group_keys(df: pd.DataFrame, baseline: bool = False) -> list[str]:
    # For Probe 2b: Animal x Timepoint x Stimulus Duration.
    # For Stage 4 baseline: Animal x Timepoint x Stimulus Duration (2 s), pooling accepted baseline sessions.
    preferred = ["Project", "Animal_ID", "Timepoint_Months", "Stimulus_Duration_s"]
    return [c for c in preferred if c in df.columns]


def apply_latency_qc(df: pd.DataFrame, baseline: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    keys = _iqr_group_keys(df, baseline=baseline)
    audits = []
    threshold_rows = []

    for label, rawcol in RAW_LATENCY_COLS.items():
        if rawcol not in df.columns:
            continue
        cleancol = f"{label}_Touch_Latency_AnalysisClean_s" if label != "Reward" else "Reward_Retrieval_Latency_AnalysisClean_s"
        exclcol = f"{label}_Latency_Analysis_Excluded"
        reasoncol = f"{label}_Latency_Analysis_QC_Reason"
        q1col = f"{label}_Analysis_IQR_Q1_s"
        q3col = f"{label}_Analysis_IQR_Q3_s"
        iqrcol = f"{label}_Analysis_IQR_s"
        uppercol = f"{label}_Analysis_IQR_Upper_s"
        ncol = f"{label}_Analysis_IQR_n"

        df[cleancol] = df[rawcol]
        df[exclcol] = False
        df[reasoncol] = "NOT_APPLICABLE"
        # Threshold columns are added by the group-statistics merge below.

        # Only derive thresholds from analysis-eligible, nonmissing, positive raw latencies.
        eligible_mask = df["Analysis_Eligible"].fillna(False) & df[rawcol].notna() & (df[rawcol] > 0)
        source = df.loc[eligible_mask, keys + [rawcol]].copy()

        if source.empty:
            continue

        grouped = source.groupby(keys, dropna=False)[rawcol]
        stat = grouped.agg(
            n="count",
            q1=lambda x: x.quantile(0.25),
            q3=lambda x: x.quantile(0.75),
        ).reset_index()
        stat["iqr"] = stat["q3"] - stat["q1"]
        stat["upper"] = stat["q3"] + IQR_MULTIPLIER * stat["iqr"]
        stat["latency_type"] = label
        threshold_rows.append(stat.copy())

        renamed = stat.rename(columns={"n": ncol, "q1": q1col, "q3": q3col, "iqr": iqrcol, "upper": uppercol})
        df = df.merge(renamed[keys + [ncol, q1col, q3col, iqrcol, uppercol]], on=keys, how="left", validate="many_to_one")

        applicable = df[rawcol].notna()
        df.loc[applicable, reasoncol] = "KEPT"

        nonpositive = applicable & (df[rawcol] <= 0)
        df.loc[nonpositive, exclcol] = True
        df.loc[nonpositive, reasoncol] = "NONPOSITIVE_LATENCY"
        df.loc[nonpositive, cleancol] = np.nan

        low_n = applicable & ~nonpositive & (df[ncol].fillna(0) < MIN_IQR_N)
        df.loc[low_n, reasoncol] = f"KEPT_INSUFFICIENT_N_LT_{MIN_IQR_N}"

        high = applicable & ~nonpositive & (df[ncol].fillna(0) >= MIN_IQR_N) & (df[rawcol] > df[uppercol])
        df.loc[high, exclcol] = True
        df.loc[high, reasoncol] = f"EXCLUDED_GT_Q3_PLUS_{IQR_MULTIPLIER:g}IQR"
        df.loc[high, cleancol] = np.nan

        # Rows not eligible are never used for inferential analysis; do not call them latency outliers.
        not_elig = applicable & ~df["Analysis_Eligible"].fillna(False)
        df.loc[not_elig, reasoncol] = "NOT_ANALYSIS_ELIGIBLE"

        audit_cols = [c for c in META_COLS + ["Probe_Session_Number", "Baseline_Day_Number", "Source_Database", "SID", "Session_DateTime", "Trial_Index", "Outcome", "Stimulus_Duration_s"] if c in df.columns]
        a = df.loc[df[exclcol], audit_cols + [rawcol, q1col, q3col, iqrcol, uppercol, ncol, reasoncol]].copy()
        if not a.empty:
            a.insert(0, "Latency_Type", label)
            a = a.rename(columns={rawcol: "Raw_Latency_s", q1col:"Q1_s", q3col:"Q3_s", iqrcol:"IQR_s", uppercol:"Upper_Cutoff_s", ncol:"Threshold_n", reasoncol:"Exclusion_Reason"})
            audits.append(a)

    audit = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame()
    thresholds = pd.concat(threshold_rows, ignore_index=True) if threshold_rows else pd.DataFrame()
    return df, audit, thresholds


def loglinear_rates(h, m, fa, cr):
    # Hautus-style log-linear correction: add 0.5 to every cell.
    h = float(h); m = float(m); fa = float(fa); cr = float(cr)
    signal = h + m
    noise = fa + cr
    hr = h / signal if signal > 0 else np.nan
    far = fa / noise if noise > 0 else np.nan
    hr_corr = (h + 0.5) / (signal + 1.0) if signal >= 0 else np.nan
    far_corr = (fa + 0.5) / (noise + 1.0) if noise >= 0 else np.nan
    dprime = norm.ppf(hr_corr) - norm.ppf(far_corr) if np.isfinite(hr_corr) and np.isfinite(far_corr) else np.nan
    c = -0.5 * (norm.ppf(hr_corr) + norm.ppf(far_corr)) if np.isfinite(hr_corr) and np.isfinite(far_corr) else np.nan
    return hr, far, hr_corr, far_corr, dprime, c


def make_session_metrics(df: pd.DataFrame, baseline: bool = False) -> pd.DataFrame:
    d = df.loc[df["Analysis_Eligible"].fillna(False) & df["Core_Trial"].fillna(False)].copy()
    if d.empty:
        return pd.DataFrame()

    session_keys = ["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label"]
    for c in (["Probe_Session_Number"] if not baseline else ["Baseline_Day_Number", "Baseline_Status"]):
        if c in d.columns: session_keys.append(c)
    for c in ["Source_Database","SID","Session_DateTime","Stimulus_Duration_s"]:
        if c in d.columns: session_keys.append(c)

    aggs = {"Hit":"sum","Miss":"sum","False_Alarm":"sum","Correct_Rejection":"sum"}
    cleanmap = {
        "Correct_Touch_Latency_AnalysisClean_s": "Mean_Correct_Touch_Latency_s",
        "Incorrect_Touch_Latency_AnalysisClean_s": "Mean_Incorrect_Touch_Latency_s",
        "Reward_Retrieval_Latency_AnalysisClean_s": "Mean_Reward_Retrieval_Latency_s",
    }
    for c in cleanmap:
        if c in d.columns: aggs[c] = "mean"
    out = d.groupby(session_keys, dropna=False).agg(aggs).reset_index()
    out = out.rename(columns=cleanmap)

    vals=[]
    for _,r in out.iterrows():
        hr,far,hrc,farc,dp,cc = loglinear_rates(r.Hit,r.Miss,r.False_Alarm,r.Correct_Rejection)
        vals.append((hr,far,hrc,farc,dp,cc))
    metrics = pd.DataFrame(vals, columns=["Hit_Rate","False_Alarm_Rate","Hit_Rate_LogLinear","False_Alarm_Rate_LogLinear","d_prime","criterion_c"], index=out.index)
    out = pd.concat([out, metrics], axis=1)
    out["Signal_Trials"] = out["Hit"] + out["Miss"]
    out["Noise_Trials"] = out["False_Alarm"] + out["Correct_Rejection"]
    out["Core_Trials"] = out["Signal_Trials"] + out["Noise_Trials"]
    return out


def make_animal_condition_summary(session_df: pd.DataFrame, baseline: bool=False) -> pd.DataFrame:
    if session_df.empty: return pd.DataFrame()
    keys=["Project","Animal_ID","Cohort","Sex","Genotype","Treatment","Timepoint_Months","Timepoint_Label","Stimulus_Duration_s"]
    keys=[c for c in keys if c in session_df.columns]
    rows=[]
    for k,g in session_df.groupby(keys, dropna=False):
        if not isinstance(k, tuple): k=(k,)
        row=dict(zip(keys,k))
        h=g["Hit"].sum(); m=g["Miss"].sum(); fa=g["False_Alarm"].sum(); cr=g["Correct_Rejection"].sum()
        hr,far,hrc,farc,dp,cc=loglinear_rates(h,m,fa,cr)
        row.update({
            "Hits":h,"Misses":m,"False_Alarms":fa,"Correct_Rejections":cr,
            "Signal_Trials":h+m,"Noise_Trials":fa+cr,"Core_Trials":h+m+fa+cr,
            "Hit_Rate":hr,"False_Alarm_Rate":far,
            "Hit_Rate_LogLinear":hrc,"False_Alarm_Rate_LogLinear":farc,
            "d_prime":dp,"criterion_c":cc,
            "Sessions_Used": int(len(g)),
        })
        if not baseline and "Probe_Session_Number" in g.columns:
            row["Probe_Sessions_Used"] = ";".join(str(int(x)) for x in sorted(pd.Series(g["Probe_Session_Number"].dropna().unique()).astype(int)))
        if baseline and "Baseline_Day_Number" in g.columns:
            row["Baseline_Days_Used"] = ";".join(str(int(x)) for x in sorted(pd.Series(g["Baseline_Day_Number"].dropna().unique()).astype(int)))
        for c in ["Mean_Correct_Touch_Latency_s","Mean_Incorrect_Touch_Latency_s","Mean_Reward_Retrieval_Latency_s"]:
            if c in g.columns:
                row[c.replace("Mean_", "Mean_Session_")] = g[c].mean(skipna=True)
                row[c.replace("Mean_", "Sessions_With_")] = int(g[c].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows)


def make_eligibility_audit(df: pd.DataFrame, is_probe: bool) -> pd.DataFrame:
    keys=[c for c in META_COLS + (["Probe_Session_Number"] if is_probe else ["Baseline_Day_Number","Baseline_Status"]) + ["Source_Database","SID","Session_DateTime","Schedule_Name"] if c in df.columns]
    audit=df.groupby(keys + ["Analysis_Eligible","Analysis_Eligibility_Reason"], dropna=False).size().reset_index(name="Trial_Rows")
    return audit


def make_qc_summary(df: pd.DataFrame, label: str) -> pd.DataFrame:
    rows=[]
    base={"Dataset":label,"Rows":len(df),"Animals":df["Animal_ID"].nunique() if "Animal_ID" in df else np.nan}
    rows.append({**base,"QC_Item":"Analysis eligible rows","Count":int(df["Analysis_Eligible"].sum()),"Percent":100*df["Analysis_Eligible"].mean()})
    for lat in ["Correct","Incorrect","Reward"]:
        raw=RAW_LATENCY_COLS[lat]
        ex=f"{lat}_Latency_Analysis_Excluded"
        if raw in df and ex in df:
            n=int(df[raw].notna().sum()); x=int(df[ex].sum())
            rows.append({**base,"QC_Item":f"{lat} latency excluded","Count":x,"Percent":100*x/n if n else np.nan})
    return pd.DataFrame(rows)


def rebuild_next_trial(probe_qc: pd.DataFrame) -> pd.DataFrame:
    d=probe_qc.loc[probe_qc["Analysis_Eligible"].fillna(False)].copy()
    sortcols=[c for c in ["Project","Animal_ID","Timepoint_Months","Probe_Session_Number","Source_Database","SID","Trial_Index"] if c in d.columns]
    d=d.sort_values(sortcols, kind="stable")
    groupcols=[c for c in ["Project","Animal_ID","Timepoint_Months","Probe_Session_Number","Source_Database","SID"] if c in d.columns]
    # Prefer extractor-provided previous-class mapping when available, because it reflects ABET trial semantics.
    if "Previous_Outcome_Class" not in d.columns:
        d["Previous_Trial_Outcome"] = d.groupby(groupcols, dropna=False)["Outcome"].shift(1)
        prev=d["Previous_Trial_Outcome"].astype(str)
        d["Previous_Outcome_Class"] = np.select(
            [prev.isin(["Hit","Correct Rejection"]), prev.isin(["Miss","False Alarm","Correction Trial Mistake"])],
            ["After correct trial","After error/miss"], default=np.nan)
    keep=d["Previous_Outcome_Class"].notna() & d["Core_Trial"].fillna(False)
    cols=[c for c in META_COLS + ["Probe_Session_Number","Source_Database","SID","Trial_Index","Stimulus_Duration_s","Previous_Trial_Outcome","Previous_Outcome_Class","Outcome","Hit","Miss","False_Alarm","Correct_Rejection","Correct_Touch_Latency_AnalysisClean_s","Incorrect_Touch_Latency_AnalysisClean_s","Reward_Retrieval_Latency_AnalysisClean_s"] if c in d.columns]
    out=d.loc[keep, cols].copy()
    out=out.rename(columns={"Outcome":"Current_Outcome","Hit":"Current_Hit","Miss":"Current_Miss","False_Alarm":"Current_False_Alarm","Correct_Rejection":"Current_Correct_Rejection"})
    return out


def make_baseline_probe_long(base_summary: pd.DataFrame, probe_summary: pd.DataFrame) -> pd.DataFrame:
    pieces=[]
    if not base_summary.empty:
        b=base_summary.copy(); b["Phase"]="Stage 4 baseline"; pieces.append(b)
    if not probe_summary.empty:
        p=probe_summary.loc[pd.to_numeric(probe_summary["Stimulus_Duration_s"],errors="coerce").eq(2.0)].copy()
        p["Phase"]="Probe 2b - 2.0 s"; pieces.append(p)
    if not pieces: return pd.DataFrame()
    common=set(pieces[0].columns)
    for x in pieces[1:]: common &= set(x.columns)
    ordered=[c for c in META_COLS + ["Stimulus_Duration_s","Phase","Hits","Misses","False_Alarms","Correct_Rejections","Signal_Trials","Noise_Trials","Core_Trials","Hit_Rate","False_Alarm_Rate","Hit_Rate_LogLinear","False_Alarm_Rate_LogLinear","d_prime","criterion_c","Mean_Session_Correct_Touch_Latency_s","Mean_Session_Incorrect_Touch_Latency_s","Mean_Session_Reward_Retrieval_Latency_s","Sessions_Used"] if c in common or c=="Phase"]
    # concat full union, then put key columns first
    out=pd.concat(pieces, ignore_index=True, sort=False)
    front=[c for c in META_COLS + ["Phase","Stimulus_Duration_s"] if c in out.columns]
    rest=[c for c in out.columns if c not in front]
    return out[front+rest]


def _holm_adjust(pvals: list[float]) -> list[float]:
    arr=np.asarray(pvals,dtype=float)
    out=np.full(len(arr),np.nan)
    good=np.where(np.isfinite(arr))[0]
    if len(good)==0: return out.tolist()
    order=good[np.argsort(arr[good])]
    m=len(order); running=0.0
    for rank,idx in enumerate(order):
        adj=(m-rank)*arr[idx]
        running=max(running,adj)
        out[idx]=min(1.0,running)
    return out.tolist()


def _control_treated_levels(project: str, observed: list[str]) -> tuple[str|None,str|None]:
    levels=[str(x) for x in observed if pd.notna(x)]
    low={x.lower():x for x in levels}
    if project.lower()=="lecanemab":
        return low.get("pbs"), low.get("lecanemab")
    if project.lower()=="vaccine":
        return low.get("sham"), low.get("vaccine")
    # Generic fallback: only when exactly two levels are present; alphabetical first is reference.
    if len(levels)==2:
        lev=sorted(levels)
        return lev[0],lev[1]
    return None,None


def _model_formula(outcome: str) -> str:
    # Pre-specified hierarchical model. This is deliberately smaller than a five-way interaction,
    # while retaining the biologically important Genotype x Treatment moderation by Sex, Age and SD.
    rhs=(
        "C(Genotype)*C(Treatment)*C(Sex) + "
        "C(Genotype)*C(Treatment)*C(Timepoint_Months) + "
        "C(Genotype)*C(Treatment)*C(Stimulus_Duration_s) + "
        "C(Sex)*C(Timepoint_Months) + C(Sex)*C(Stimulus_Duration_s)"
    )
    return f"Q('{outcome}') ~ {rhs}"


def _fit_repeated_model(formula: str, dd: pd.DataFrame):
    """Fit random-intercept LMM first; use GEE only when LMM is numerically unusable."""
    errors=[]
    if smf is None:
        raise RuntimeError("statsmodels is unavailable")
    # MixedLM attempts. Powell often succeeds when LBFGS fails at a boundary variance.
    for method in ["lbfgs","powell","cg"]:
        try:
            md=smf.mixedlm(formula, dd, groups=dd["Animal_ID"], re_formula="1")
            fit=md.fit(method=method, reml=False, maxiter=1200, disp=False)
            if bool(getattr(fit,"converged",False)) and np.all(np.isfinite(np.asarray(fit.fe_params,dtype=float))):
                return "LMM_RANDOM_INTERCEPT", md, fit, method, errors
            errors.append(f"MixedLM {method}: did not converge")
        except Exception as e:
            errors.append(f"MixedLM {method}: {type(e).__name__}: {str(e)[:180]}")
    # Robust repeated-measures fallback. Same fixed-effect formula and animal clustering.
    if sm is not None:
        try:
            gee=smf.gee(formula, groups="Animal_ID", data=dd,
                        cov_struct=sm.cov_struct.Exchangeable(), family=sm.families.Gaussian())
            fit=gee.fit(maxiter=2000, ctol=1e-8)
            return "GEE_EXCHANGEABLE_FALLBACK", gee, fit, "GEE", errors
        except Exception as e:
            errors.append(f"GEE: {type(e).__name__}: {str(e)[:180]}")
    raise RuntimeError(" | ".join(errors))


def _fixed_param_info(method: str, model, fit):
    if method.startswith("LMM"):
        names=list(model.exog_names)
        beta=np.asarray(fit.fe_params,dtype=float)
        cov=np.asarray(fit.cov_params(),dtype=float)[:len(beta),:len(beta)]
    else:
        names=list(model.exog_names)
        beta=np.asarray(fit.params,dtype=float)
        cov=np.asarray(fit.cov_params(),dtype=float)
    return names,beta,cov


def _omnibus_terms(project: str, outcome: str, method: str, model, fit, n: int, animals: int) -> list[dict]:
    """Return factor-level Wald tests without silently swallowing failures."""
    rows=[]
    # First choice: statsmodels' own term-wise Wald tests from the formula design.
    try:
        wt=fit.wald_test_terms(skip_single=False, scalar=True)
        table=getattr(wt,"table",None)
        if table is not None:
            for term,row in table.iterrows():
                if str(term)=="Intercept":
                    continue
                stat=row.get("statistic", np.nan)
                p=row.get("pvalue", np.nan)
                df=row.get("df_constraint", np.nan)
                try: stat=float(np.asarray(stat).squeeze())
                except Exception: stat=np.nan
                try: p=float(np.asarray(p).squeeze())
                except Exception: p=np.nan
                try: df=float(np.asarray(df).squeeze())
                except Exception: df=np.nan
                rows.append({"Project":project,"Outcome":outcome,"Method":method,"Term":str(term),
                             "Wald_Chi2":stat,"df":df,"p_value":p,
                             "N_rows":n,"N_animals":animals,"Omnibus_Source":"statsmodels_wald_test_terms"})
            if rows:
                return rows
    except Exception as e:
        primary_error=f"{type(e).__name__}: {str(e)[:300]}"
    else:
        primary_error="wald_test_terms returned no usable rows"

    # Fallback: calculate a joint Wald test from each Patsy term slice.
    try:
        names,beta,cov=_fixed_param_info(method,model,fit)
        di=getattr(model.data,"design_info",None)
        if di is None and hasattr(getattr(model.data,"orig_exog",None),"design_info"):
            di=model.data.orig_exog.design_info
        if di is None:
            return [{"Project":project,"Outcome":outcome,"Method":method,"Term":"__OMNIBUS_EXPORT_ERROR__",
                     "Wald_Chi2":np.nan,"df":np.nan,"p_value":np.nan,"N_rows":n,"N_animals":animals,
                     "Omnibus_Source":"error","Detail":f"No design_info; primary={primary_error}"}]
        for term,sl in di.term_name_slices.items():
            if str(term)=="Intercept":
                continue
            idx=list(range(sl.start,sl.stop))
            if not idx:
                continue
            b=np.asarray(beta[idx],dtype=float)
            V=np.asarray(cov[np.ix_(idx,idx)],dtype=float)
            rank=int(np.linalg.matrix_rank(V))
            if rank<=0:
                stat=np.nan; dft=np.nan; p=np.nan
            else:
                stat=float(b.T@np.linalg.pinv(V)@b)
                dft=rank
                p=float(chi2.sf(stat,dft))
            rows.append({"Project":project,"Outcome":outcome,"Method":method,"Term":str(term),
                         "Wald_Chi2":stat,"df":dft,"p_value":p,
                         "N_rows":n,"N_animals":animals,"Omnibus_Source":"manual_term_slice"})
    except Exception as e:
        rows.append({"Project":project,"Outcome":outcome,"Method":method,"Term":"__OMNIBUS_EXPORT_ERROR__",
                     "Wald_Chi2":np.nan,"df":np.nan,"p_value":np.nan,"N_rows":n,"N_animals":animals,
                     "Omnibus_Source":"error",
                     "Detail":f"primary={primary_error}; fallback={type(e).__name__}: {str(e)[:300]}"})
    return rows


def _planned_treatment_contrasts(project: str, outcome: str, method: str, model, fit,
                                 dd: pd.DataFrame, n: int, animals: int) -> list[dict]:
    rows=[]
    if build_design_matrices is None: return rows
    control,treated=_control_treated_levels(project, dd["Treatment"].dropna().unique().tolist())
    if control is None or treated is None: return rows
    names,beta,cov=_fixed_param_info(method,model,fit)
    # MixedLM does not always expose design_info directly on model.data.
    # Recover it from the original Patsy exogenous matrix, as used by the omnibus exporter.
    di=getattr(model.data,"design_info",None)
    if di is None and hasattr(getattr(model.data,"orig_exog",None),"design_info"):
        di=model.data.orig_exog.design_info
    if di is None:
        return rows
    cats={c:sorted(dd[c].dropna().unique().tolist(), key=lambda x:str(x)) for c in ["Genotype","Sex","Timepoint_Months","Stimulus_Duration_s"]}
    for geno in cats["Genotype"]:
      for sex in cats["Sex"]:
       for tp in cats["Timepoint_Months"]:
        for sd in cats["Stimulus_Duration_s"]:
            # Require actual observations from both treatments for this cell.
            obs=dd[(dd.Genotype==geno)&(dd.Sex==sex)&(dd.Timepoint_Months==tp)&(dd.Stimulus_Duration_s==sd)]
            have=set(obs.Treatment.dropna().astype(str))
            if control not in have or treated not in have: continue
            new=pd.DataFrame([
                {"Genotype":geno,"Treatment":control,"Sex":sex,"Timepoint_Months":tp,"Stimulus_Duration_s":sd},
                {"Genotype":geno,"Treatment":treated,"Sex":sex,"Timepoint_Months":tp,"Stimulus_Duration_s":sd},
            ])
            try:
                X=np.asarray(build_design_matrices([di],new,return_type="dataframe")[0],dtype=float)
                dvec=X[1]-X[0]
                est=float(dvec@beta); se=float(np.sqrt(max(0,dvec@cov@dvec)))
                z=est/se if se>0 else np.nan
                p=float(2*norm.sf(abs(z))) if np.isfinite(z) else np.nan
                rows.append({"Project":project,"Outcome":outcome,"Method":method,
                             "Contrast":f"{treated} - {control}","Control":control,"Treated":treated,
                             "Genotype":geno,"Sex":sex,"Timepoint_Months":tp,"Stimulus_Duration_s":sd,
                             "Estimate":est,"SE":se,"z":z,"p_value":p,
                             "CI95_Lower":est-1.96*se if np.isfinite(se) else np.nan,
                             "CI95_Upper":est+1.96*se if np.isfinite(se) else np.nan,
                             "N_cell_control_animals":obs.loc[obs.Treatment.astype(str)==control,"Animal_ID"].nunique(),
                             "N_cell_treated_animals":obs.loc[obs.Treatment.astype(str)==treated,"Animal_ID"].nunique(),
                             "N_rows_model":n,"N_animals_model":animals})
            except Exception:
                continue
    if rows:
        adj=_holm_adjust([r["p_value"] for r in rows])
        for r,a in zip(rows,adj): r["p_Holm_within_Project_Outcome"]=a
    return rows


def fit_mixed_models(animal_summary: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    coeff=[]; status=[]; omnibus=[]; contrasts=[]
    if smf is None or animal_summary.empty:
        return (pd.DataFrame(), pd.DataFrame([{"Status":"statsmodels unavailable or no analysis data"}]), pd.DataFrame(), pd.DataFrame())
    outcomes=[
        "Hit_Rate","False_Alarm_Rate","d_prime","criterion_c",
        "Mean_Session_Correct_Touch_Latency_s","Mean_Session_Incorrect_Touch_Latency_s","Mean_Session_Reward_Retrieval_Latency_s"
    ]
    req=["Animal_ID","Genotype","Treatment","Sex","Timepoint_Months","Stimulus_Duration_s"]
    for project,dp in animal_summary.groupby("Project",dropna=False):
        project=str(project)
        for outcome in outcomes:
            if outcome not in dp.columns: continue
            dd=dp[req+[outcome]].dropna().copy()
            n=len(dd); animals=dd["Animal_ID"].nunique()
            if n<80 or animals<12 or dd[outcome].nunique()<5:
                status.append({"Project":project,"Outcome":outcome,"Status":"SKIPPED_INSUFFICIENT_DATA","N_rows":n,"N_animals":animals})
                continue
            # The same model requires all five factors to vary.
            levels={c:dd[c].nunique() for c in ["Genotype","Treatment","Sex","Timepoint_Months","Stimulus_Duration_s"]}
            if any(v<2 for v in levels.values()):
                status.append({"Project":project,"Outcome":outcome,"Status":"SKIPPED_FACTOR_WITH_ONE_LEVEL","N_rows":n,"N_animals":animals,"Detail":json.dumps(levels)})
                continue
            formula=_model_formula(outcome)
            try:
                method,model,fit,optimizer,errors=_fit_repeated_model(formula,dd)
            except Exception as e:
                status.append({"Project":project,"Outcome":outcome,"Status":"MODEL_FAILED","N_rows":n,"N_animals":animals,"Model":formula,"Detail":str(e)[:900]})
                continue
            names,beta,cov=_fixed_param_info(method,model,fit)
            if method.startswith("LMM"):
                se=np.asarray(fit.bse_fe,dtype=float)
            else:
                se=np.asarray(fit.bse,dtype=float)
            for i,(term,est) in enumerate(zip(names,beta)):
                sei=float(se[i]) if i<len(se) else np.nan
                z=float(est/sei) if np.isfinite(sei) and sei>0 else np.nan
                pv=float(2*norm.sf(abs(z))) if np.isfinite(z) else np.nan
                coeff.append({"Project":project,"Outcome":outcome,"Method":method,"Model":formula,"Term":term,
                              "Estimate":float(est),"SE":sei,"z_or_t":z,"p_value":pv,
                              "CI95_Lower":float(est-1.96*sei) if np.isfinite(sei) else np.nan,
                              "CI95_Upper":float(est+1.96*sei) if np.isfinite(sei) else np.nan,
                              "N_rows":n,"N_animals":animals})
            omnibus.extend(_omnibus_terms(project,outcome,method,model,fit,n,animals))
            contrasts.extend(_planned_treatment_contrasts(project,outcome,method,model,fit,dd,n,animals))
            conv=getattr(fit,"converged",None)
            if conv is None:
                fit_status="MODEL_FIT_CONVERGENCE_NOT_REPORTED"
                conv_value=""
            elif bool(conv):
                fit_status="MODEL_FIT"
                conv_value=True
            else:
                fit_status="MODEL_FIT_WARNING_NONCONVERGED"
                conv_value=False
            status.append({"Project":project,"Outcome":outcome,"Status":fit_status,"N_rows":n,"N_animals":animals,
                           "Method":method,"Optimizer":optimizer,"Model":formula,
                           "Converged":conv_value,
                           "Detail":" | ".join(errors)[-900:] if errors else ""})
    return pd.DataFrame(coeff),pd.DataFrame(status),pd.DataFrame(omnibus),pd.DataFrame(contrasts)


def make_sample_counts(session_df: pd.DataFrame) -> pd.DataFrame:
    if session_df.empty: return pd.DataFrame()
    group=[c for c in ["Project","Cohort","Genotype","Treatment","Sex","Timepoint_Months"] if c in session_df.columns]
    out=(session_df.groupby(group,dropna=False)
         .agg(Animals=("Animal_ID","nunique"),Sessions=("SID","nunique") if "SID" in session_df.columns else ("Animal_ID","size"))
         .reset_index())
    return out


def split_eligibility_audit(audit: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    if audit.empty: return audit.copy(),audit.copy()
    inc=audit.loc[audit["Analysis_Eligible"].fillna(False)].copy()
    exc=audit.loc[~audit["Analysis_Eligible"].fillna(False)].copy()
    return inc,exc

def write_csv(df: pd.DataFrame, out: Path):
    if df is None: return
    df.to_csv(out, index=False)


def build_readme(outdir: Path, probe_path: Path, base_path: Path|None, files_written: list[str]):
    txt=f"""ATLAS CPT ANALYSIS MODULE OUTPUT\nGenerated: {datetime.now().isoformat(timespec='seconds')}\n\nINPUTS\nProbe 2b: {probe_path}\nStage 4: {base_path if base_path else 'Not provided'}\n\nPRIMARY RULES\n- Atlas source masters are never modified.\n- Project-specific treatment labels are validated before QC/statistics.\n- Approved reconciliation: Lecanemab AS204M3 is normalized to PBS; any other unexpected treatment label stops the analysis.\n- Mouse is the biological experimental unit.\n- First {FIRST_N_PROBE_SESSIONS} Probe 2b sessions per time point are eligible for primary analysis.\n- Lecanemab Cohort 1: 6 and 9 months eligible; 12 months excluded from treatment analysis.\n- Correction trials are not counted as core Hit/Miss/False Alarm/Correct Rejection trials.\n- Latency QC is recalculated from RAW latency columns.\n- Extreme latency threshold: Q3 + {IQR_MULTIPLIER:g} x IQR.\n- Threshold strata: Project x Animal x Timepoint x Stimulus Duration.\n- Minimum threshold sample size: n={MIN_IQR_N}; below this, values are retained and flagged as insufficient for automatic outlier screening.\n- Hits, misses, false alarms and correct rejections are never deleted because of latency QC.\n- d-prime and criterion use the log-linear 0.5-cell correction.
- Primary repeated-measures model uses one pre-specified hierarchical fixed-effect formula for both projects.
- Random-intercept LMM is attempted first. If numerically singular, the same fixed-effect formula is fit with an exchangeable GEE and the fallback is labeled explicitly.
- Planned treatment contrasts compare treated vs control within Genotype x Sex x Timepoint x Stimulus Duration cells and use Holm adjustment within each Project x Outcome family.\n\nFILES WRITTEN\n""" + "\n".join(f"- {x}" for x in files_written) + "\n"
    (outdir/"README_ANALYSIS_OUTPUT.txt").write_text(txt, encoding="utf-8")


def run(input_folder: Path):
    probe_path=find_input(input_folder,"PROBE2B_TRIAL_MASTER")
    if probe_path is None:
        raise FileNotFoundError("Could not find PROBE2B_TRIAL_MASTER (.csv/.xlsx/.parquet) in selected folder.")
    base_path=find_input(input_folder,"STAGE4_BASELINE_TRIAL_MASTER")

    outdir=input_folder/OUTPUT_FOLDER_NAME
    outdir.mkdir(exist_ok=True)
    files_written=[]

    print(f"Reading Probe 2b trial master: {probe_path.name}")
    probe=clean_common(read_table(probe_path))
    probe, probe_metadata_audit = normalize_and_validate_treatments(probe, "Probe2b")
    probe=apply_analysis_eligibility(probe,is_probe=True)
    probe=add_core_trial_flag(probe)
    probe_qc, probe_outliers, probe_thresholds=apply_latency_qc(probe,baseline=False)
    probe_sessions=make_session_metrics(probe_qc,baseline=False)
    probe_animal=make_animal_condition_summary(probe_sessions,baseline=False)
    probe_elig=make_eligibility_audit(probe_qc,is_probe=True)
    next_trial=rebuild_next_trial(probe_qc)

    outputs={
        "ANALYSIS_PROBE2B_TRIAL_QC.csv":probe_qc,
        "ANALYSIS_PROBE2B_OUTLIER_AUDIT.csv":probe_outliers,
        "ANALYSIS_PROBE2B_IQR_THRESHOLDS.csv":probe_thresholds,
        "ANALYSIS_PROBE2B_ELIGIBILITY_AUDIT.csv":probe_elig,
        "ANALYSIS_PROBE2B_SESSION_METRICS.csv":probe_sessions,
        "ANALYSIS_PROBE2B_ANIMAL_CONDITION.csv":probe_animal,
        "ANALYSIS_NEXT_TRIAL.csv":next_trial,
        "ANALYSIS_METADATA_TREATMENT_AUDIT.csv":probe_metadata_audit,
    }

    qc_summary=[make_qc_summary(probe_qc,"Probe2b")]
    baseline_animal=pd.DataFrame()
    if base_path is not None:
        print(f"Reading Stage 4 baseline trial master: {base_path.name}")
        base=clean_common(read_table(base_path))
        base, base_metadata_audit = normalize_and_validate_treatments(base, "Stage4")
        if not base_metadata_audit.empty:
            outputs["ANALYSIS_METADATA_TREATMENT_AUDIT.csv"] = pd.concat(
                [outputs["ANALYSIS_METADATA_TREATMENT_AUDIT.csv"], base_metadata_audit],
                ignore_index=True
            )
        base=apply_analysis_eligibility(base,is_probe=False)
        base=add_core_trial_flag(base)
        base_qc, base_outliers, base_thresholds=apply_latency_qc(base,baseline=True)
        base_sessions=make_session_metrics(base_qc,baseline=True)
        baseline_animal=make_animal_condition_summary(base_sessions,baseline=True)
        base_elig=make_eligibility_audit(base_qc,is_probe=False)
        outputs.update({
            "ANALYSIS_STAGE4_TRIAL_QC.csv":base_qc,
            "ANALYSIS_STAGE4_OUTLIER_AUDIT.csv":base_outliers,
            "ANALYSIS_STAGE4_IQR_THRESHOLDS.csv":base_thresholds,
            "ANALYSIS_STAGE4_ELIGIBILITY_AUDIT.csv":base_elig,
            "ANALYSIS_STAGE4_SESSION_METRICS.csv":base_sessions,
            "ANALYSIS_STAGE4_ANIMAL_CONDITION.csv":baseline_animal,
            "ANALYSIS_BASELINE_TO_PROBE_2S_LONG.csv":make_baseline_probe_long(baseline_animal,probe_animal),
        })
        qc_summary.append(make_qc_summary(base_qc,"Stage4"))

    # Transparent sample manifests for postdoc review.
    probe_included,probe_excluded=split_eligibility_audit(probe_elig)
    outputs["ANALYSIS_PROBE2B_INCLUDED_SESSIONS.csv"]=probe_included
    outputs["ANALYSIS_PROBE2B_EXCLUDED_SESSIONS.csv"]=probe_excluded
    outputs["ANALYSIS_INCLUDED_SAMPLE_COUNTS.csv"]=make_sample_counts(probe_sessions)

    model_results, model_status, model_omnibus, model_contrasts=fit_mixed_models(probe_animal)
    outputs["ANALYSIS_MIXED_MODEL_COEFFICIENTS.csv"]=model_results
    outputs["ANALYSIS_MIXED_MODEL_STATUS.csv"]=model_status
    outputs["ANALYSIS_MIXED_MODEL_OMNIBUS.csv"]=model_omnibus
    outputs["ANALYSIS_PLANNED_TREATMENT_CONTRASTS.csv"]=model_contrasts
    outputs["ANALYSIS_QC_SUMMARY.csv"]=pd.concat(qc_summary,ignore_index=True)

    for name,df in outputs.items():
        write_csv(df,outdir/name); files_written.append(name)
    build_readme(outdir,probe_path,base_path,files_written)
    files_written.append("README_ANALYSIS_OUTPUT.txt")

    print("\nDONE")
    print(f"Output folder: {outdir}")
    for f in files_written: print(" -",f)
    return outdir


def choose_folder_gui() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
        folder=filedialog.askdirectory(title="Select folder containing Atlas Extractor trial masters")
        root.destroy()
        return Path(folder) if folder else None
    except Exception:
        return None


def main():
    print("="*72)
    print("ATLAS CPT ANALYSIS MODULE v1.5")
    print("Trial QC -> eligibility manifests -> CPT metrics -> repeated-measures models -> planned contrasts")
    print("="*72)
    if len(sys.argv)>1:
        folder=Path(sys.argv[1].strip('"')).expanduser().resolve()
    else:
        folder=choose_folder_gui()
        if folder is None:
            raw=input("Folder containing PROBE2B_TRIAL_MASTER: ").strip().strip('"')
            if not raw: return
            folder=Path(raw).expanduser().resolve()
    try:
        run(folder)
    except Exception as e:
        print("\nERROR:",e)
        traceback.print_exc()
        input("\nPress Enter to close...")
        raise
    input("\nPress Enter to close...")

if __name__=="__main__":
    main()
