
from __future__ import annotations

import sys, traceback
import math
import textwrap
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

VERSION = "1.8"

DURS = [2.0, 1.0, 0.5, 0.2]
TPS = [6, 9, 12]
SEXES = ["Female", "Male"]

MAIN_METRICS = [
    ("Hit_Rate", "Hit rate (%)", True),
    ("False_Alarm_Rate", "False alarm rate (%)", True),
    ("d_prime", "d prime", False),
    ("criterion_c", "Response bias (c)", False),
]

LATENCY_METRICS = [
    ("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
    ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False),
]

STORY_LATENCY_METRICS = [
    ("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
    ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False),
]

METRICS = [
    *MAIN_METRICS,
    *LATENCY_METRICS,
]

COL_TO_MODEL_OUTCOME = {
    "Hit_Rate": "Hit_Rate",
    "False_Alarm_Rate": "False_Alarm_Rate",
    "d_prime": "d_prime",
    "criterion_c": "criterion_c",
    "Mean_Session_Correct_Touch_Latency_s": "Correct_Touch_Latency",
    "Mean_Session_Incorrect_Touch_Latency_s": "Incorrect_Touch_Latency",
    "Mean_Session_Reward_Retrieval_Latency_s": "Reward_Retrieval_Latency",
}

GROUP_ORDER = {
    "Lecanemab": [
        ("KI2TA-3", "PBS"),
        ("KI2TA-3", "Lecanemab"),
        ("KI2TA-4", "PBS"),
        ("KI2TA-4", "Lecanemab"),
    ],
    "Vaccine": [
        ("KI2TA-3", "Sham"),
        ("KI2TA-3", "Vaccine"),
        ("KI2TA-4", "Sham"),
        ("KI2TA-4", "Vaccine"),
    ],
}

def safe_read(path):
    if path is None or not path.exists() or path.stat().st_size <= 2:
        return pd.DataFrame()
    return pd.read_csv(path)

def find_file(root, name):
    root = Path(root)
    for p in [root / name, root / "ATLAS_ANALYSIS_OUTPUT" / name]:
        if p.exists():
            return p
    hits = list(root.rglob(name))
    return hits[0] if hits else None

def choose_folder(title):
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        p = filedialog.askdirectory(title=title)
        r.destroy()
        return p
    except Exception:
        return ""

def choose_file(title, filetypes=None):
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        p = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes or [("CSV files", "*.csv"), ("All files", "*.*")]
        )
        r.destroy()
        return p
    except Exception:
        return ""

def first_present(df, names):
    for name in names:
        if name in df.columns:
            return name
    return None

def normalize_extractor_67(raw):
    """Convert the Probe 2b extractor 67-column CSV into graph-maker columns."""
    d = raw.copy()
    rename_options = {
        "Project": ["Project", "Project_Group", "Experiment", "Study", "ProjectGroup", "ExpName"],
        "Animal_ID": ["Animal_ID", "AnimalID", "Animal", "Mouse_ID", "MouseID", "Subject", "Subject_ID"],
        "Cohort": ["Cohort", "Cohort_ID", "CohortID"],
        "Sex": ["Sex", "sex"],
        "Genotype": ["Genotype", "Strain", "ApoE_Genotype", "ApoE", "geno"],
        "Treatment": ["Treatment", "Group", "Drug", "Intervention"],
        "Timepoint_Months": ["Timepoint_Months", "AgeGroup", "Age_Group", "Timepoint", "Time_Point", "Month", "Months", "Age"],
        "Stimulus_Duration_s": ["Stimulus_Duration_s", "Stimulus_Duration", "StimDur", "StimulusDuration", "SD", "Duration"],
        "Probe_Session_Number": ["Probe_Session_Number", "Chronological_Day", "chronological day", "Probe_Day", "Session_Number", "Session"],
        "Hit_Rate": ["Hit_Rate", "HR", "HitRate", "hit_rate"],
        "False_Alarm_Rate": ["False_Alarm_Rate", "FAR", "FalseAlarmRate", "false_alarm_rate"],
        "d_prime": ["d_prime", "dprime", "D_Prime", "DPrime", "d'"],
        "criterion_c": ["criterion_c", "c", "Response_Bias", "Response_Bias_c", "Criterion"],
        "Mean_Session_Correct_Touch_Latency_s": [
            "Mean_Session_Correct_Touch_Latency_s", "Mean_Correct_Touch_Latency_s",
            "Correct_Touch_Latency", "Correct_Touch_Latency_s", "CorrectTouchLatency",
            "Correct_Touch_Latency_AnalysisClean_s"
        ],
        "Mean_Session_Incorrect_Touch_Latency_s": [
            "Mean_Session_Incorrect_Touch_Latency_s", "Mean_Incorrect_Touch_Latency_s",
            "Incorrect_Touch_Latency", "Incorrect_Touch_Latency_s", "IncorrectTouchLatency",
            "Incorrect_Touch_Latency_AnalysisClean_s"
        ],
        "Mean_Session_Reward_Retrieval_Latency_s": [
            "Mean_Session_Reward_Retrieval_Latency_s", "Mean_Reward_Retrieval_Latency_s",
            "Reward_Retrieval_Latency", "Reward_Retrieval_Latency_s", "RewardRetrievalLatency",
            "Reward_Retrieval_Latency_AnalysisClean_s"
        ],
    }
    rename = {}
    for target, options in rename_options.items():
        src = first_present(d, options)
        if src and src != target:
            rename[src] = target
    d = d.rename(columns=rename)

    # The Taylor/MouseBytes-style 67-column export is wide: one row per session
    # with separate metric columns for 0.2, 0.5, 1, and 2 s. Convert it to the
    # long format used by the graph pages.
    if "Stimulus_Duration_s" not in d.columns:
        wide_specs = {
            0.2: {
                "Hit_Rate": "Hit Rate at 0.2s SD",
                "False_Alarm_Rate": "False Alarm Rate at 0.2s SD",
                "d_prime": "dPrime at 0.2s SD",
                "criterion_c": "c Response Bias at 0.2s SD",
                "Mean_Session_Correct_Touch_Latency_s": "AVG_Average - Correct Choice Latency at 0.2s SD",
                "Mean_Session_Incorrect_Touch_Latency_s": "AVG_Average - Mistake Latency at 0.2s SD",
                "Mean_Session_Reward_Retrieval_Latency_s": "AVG_Average - Reward Retrieval Latency at 0.2s SD",
            },
            0.5: {
                "Hit_Rate": "Hit Rate at 0.5s SD",
                "False_Alarm_Rate": "False Alarm Rate at 0.5s SD",
                "d_prime": "dPrime at 0.5s SD",
                "criterion_c": "c Response Bias at 0.5s SD",
                "Mean_Session_Correct_Touch_Latency_s": "AVG_Average - Correct Choice Latency at 0.5s SD",
                "Mean_Session_Incorrect_Touch_Latency_s": "AVG_Average - Mistake Latency at 0.5s SD",
                "Mean_Session_Reward_Retrieval_Latency_s": "AVG_Average - Reward Retrieval Latency at 0.5s SD",
            },
            1.0: {
                "Hit_Rate": "Hit Rate at 1s SD",
                "False_Alarm_Rate": "False Alarm Rate at 1s SD",
                "d_prime": "dPrime at 1s SD",
                "criterion_c": "c Response Bias at 1s SD",
                "Mean_Session_Correct_Touch_Latency_s": "AVG_Average - Correct Choice Latency at 1s SD",
                "Mean_Session_Incorrect_Touch_Latency_s": "AVG_Average - Mistake Latency at 1s SD",
                "Mean_Session_Reward_Retrieval_Latency_s": "AVG_Average - Reward Retrieval Latency at 1s SD",
            },
            2.0: {
                "Hit_Rate": "Hit Rate at 2s SD",
                "False_Alarm_Rate": "False Alarm Rate at 2s SD",
                "d_prime": "dPrime at 2s SD",
                "criterion_c": "c Response Bias at 2s SD",
                "Mean_Session_Correct_Touch_Latency_s": "AVG_Average - Correct Choice Latency at 2s SD",
                "Mean_Session_Incorrect_Touch_Latency_s": "AVG_Average - Mistake Latency at 2s SD",
                "Mean_Session_Reward_Retrieval_Latency_s": "AVG_Average - Reward Retrieval Latency at 2s SD",
            },
        }
        id_cols = [c for c in ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
                               "Timepoint_Months", "Probe_Session_Number"] if c in d.columns]
        long_rows = []
        for dur, spec in wide_specs.items():
            available = {target: src for target, src in spec.items() if src in d.columns}
            if not available:
                continue
            part = d[id_cols].copy()
            part["Stimulus_Duration_s"] = dur
            for target, src in available.items():
                part[target] = d[src]
            long_rows.append(part)
        if long_rows:
            d = pd.concat(long_rows, ignore_index=True)

    required = ["Project", "Animal_ID", "Sex", "Genotype", "Treatment",
                "Timepoint_Months", "Stimulus_Duration_s"]
    missing = [c for c in required if c not in d.columns]
    if missing:
        raise ValueError(
            "The selected extractor CSV is missing graph-required columns after normalization: "
            + ", ".join(missing)
            + "\nUse the 67-column Probe 2b extractor output, not the reconciliation summary."
        )

    if "Cohort" not in d.columns:
        d["Cohort"] = ""
    if "Probe_Session_Number" not in d.columns:
        d["Probe_Session_Number"] = np.nan

    d["Project"] = d["Project"].astype(str).str.strip()
    d["Project"] = d["Project"].replace({
        "Lecanemab ": "Lecanemab",
        "Vaccine ": "Vaccine",
    })
    d["Animal_ID"] = d["Animal_ID"].astype(str).str.strip()
    d["Genotype"] = d["Genotype"].astype(str).str.strip().replace({
        "AppKI2TA-3": "KI2TA-3",
        "AppKI2TA-4": "KI2TA-4",
        "KI2TA3": "KI2TA-3",
        "KI2TA4": "KI2TA-4",
    })
    d["Sex"] = d["Sex"].astype(str).str.strip().replace({
        "F": "Female", "f": "Female", "female": "Female",
        "M": "Male", "m": "Male", "male": "Male",
    })
    d["Treatment"] = d["Treatment"].astype(str).str.strip()

    d["Timepoint_Months"] = (
        d["Timepoint_Months"].astype(str).str.extract(r"(\d+)", expand=False)
    )
    d["Timepoint_Months"] = pd.to_numeric(d["Timepoint_Months"], errors="coerce")
    d["Stimulus_Duration_s"] = pd.to_numeric(
        d["Stimulus_Duration_s"].astype(str).str.replace("s", "", regex=False),
        errors="coerce"
    )
    d["Probe_Session_Number"] = pd.to_numeric(d["Probe_Session_Number"], errors="coerce")

    metric_cols = [m[0] for m in METRICS]
    for col in metric_cols:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    for col in ["Hit_Rate", "False_Alarm_Rate"]:
        if col in d.columns and pd.to_numeric(d[col], errors="coerce").max(skipna=True) > 1.5:
            d[col] = pd.to_numeric(d[col], errors="coerce") / 100.0

    keep = [
        "Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
        "Timepoint_Months", "Stimulus_Duration_s", "Probe_Session_Number",
        *[c for c in metric_cols if c in d.columns],
    ]
    d = d[keep].copy()
    d = d.dropna(subset=["Timepoint_Months", "Stimulus_Duration_s"])
    d = d[d["Animal_ID"].astype(str).str.len() > 0]
    return clean_meta(d)

def find_sidecar_csv(folder, patterns):
    folder = Path(folder)
    hits = []
    for pat in patterns:
        hits.extend(folder.glob(pat))
    hits = [p for p in hits if p.is_file() and p.stat().st_size > 2]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None

def normalize_next_trial_csv(raw):
    d = normalize_extractor_67(raw)
    extra_options = {
        "Previous_Outcome_Class": [
            "Previous_Outcome_Class", "PreviousOutcomeClass", "Previous_Outcome",
            "Previous_Trial_Outcome", "Prev_Outcome", "Prior_Outcome"
        ],
        "Previous_Stimulus_Duration_s": [
            "Previous_Stimulus_Duration_s", "Previous_Stimulus_Duration",
            "Previous_SD_s", "Previous_Trial_Stimulus_Duration_s",
            "Prev_Stimulus_Duration_s", "Previous_Stimulus_Duration_ms"
        ],
        "Current_Hit": ["Current_Hit", "Hit", "Next_Hit"],
        "Current_Miss": ["Current_Miss", "Miss", "Next_Miss"],
        "Current_False_Alarm": ["Current_False_Alarm", "False_Alarm", "FA", "Next_False_Alarm"],
        "Current_Correct_Rejection": ["Current_Correct_Rejection", "Correct_Rejection", "CR", "Next_Correct_Rejection"],
        "Correct_Touch_Latency_AnalysisClean_s": [
            "Correct_Touch_Latency_AnalysisClean_s", "Correct_Touch_Latency_s",
            "Correct_Touch_Latency_IQRclean_s", "Mean_Session_Correct_Touch_Latency_s"
        ],
        "Incorrect_Touch_Latency_AnalysisClean_s": [
            "Incorrect_Touch_Latency_AnalysisClean_s", "Incorrect_Touch_Latency_s",
            "Incorrect_Touch_Latency_IQRclean_s", "Mean_Session_Incorrect_Touch_Latency_s"
        ],
        "Reward_Retrieval_Latency_AnalysisClean_s": [
            "Reward_Retrieval_Latency_AnalysisClean_s", "Reward_Retrieval_Latency_s",
            "Reward_Retrieval_Latency_IQRclean_s", "Mean_Session_Reward_Retrieval_Latency_s"
        ],
    }
    raw2 = raw.copy()
    rename = {}
    for target, options in extra_options.items():
        src = first_present(raw2, options)
        if src:
            rename[src] = target
    extra = raw2.rename(columns=rename)
    keys = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
            "Timepoint_Months", "Stimulus_Duration_s", "Probe_Session_Number"]
    passthrough = [c for c in extra_options if c in extra.columns]
    base = d[keys].copy()
    for c in passthrough:
        base[c] = extra[c].values if len(extra) == len(base) else extra[c]
    for c in ["Current_Hit", "Current_Miss", "Current_False_Alarm", "Current_Correct_Rejection",
              "Correct_Touch_Latency_AnalysisClean_s", "Incorrect_Touch_Latency_AnalysisClean_s",
              "Reward_Retrieval_Latency_AnalysisClean_s", "Previous_Stimulus_Duration_s"]:
        if c in base.columns:
            base[c] = pd.to_numeric(base[c], errors="coerce")
    if "Previous_Outcome_Class" not in base.columns:
        base["Previous_Outcome_Class"] = np.nan
    return clean_meta(base)

def clean_meta(df):
    d = df.copy()
    for c in ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
              "Timepoint_Label", "Previous_Outcome_Class", "Phase"]:
        if c in d.columns:
            d[c] = d[c].where(d[c].isna(), d[c].astype(str).str.strip())
    # Atlas trial/decile masters use F/M while plotting filters use Female/Male.
    # Normalize every input here, including trial-level and derived ITI data.
    if "Sex" in d.columns:
        d["Sex"] = d["Sex"].replace({"F": "Female", "M": "Male",
                                     "f": "Female", "m": "Male",
                                     "female": "Female", "male": "Male"})
    for c in ["Timepoint_Months", "Stimulus_Duration_s", "Probe_Session_Number",
              "Session_Progress_Decile"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d

def load_authoritative_metadata(root):
    """Load the postdoctoral source-of-truth animal metadata when available."""
    root = Path(root)
    candidates = []
    for base in [root, root.parent, Path(__file__).resolve().parent,
                 Path.cwd(), Path.cwd().parent]:
        exact = base / "ATLAS_ANIMAL_METADATA.csv"
        if exact.exists() and exact.stat().st_size > 2:
            candidates.append(exact)
    path = candidates[0] if candidates else None
    if path is None:
        fallback = []
        for base in [root, root.parent, Path(__file__).resolve().parent,
                     Path.cwd(), Path.cwd().parent]:
            fallback.extend(base.glob("ATLAS_ANIMAL_METADATA*.csv"))
        fallback = [p for p in fallback if p.exists() and p.stat().st_size > 2]
        path = max(fallback, key=lambda p: p.stat().st_mtime) if fallback else None
    if path is None:
        return pd.DataFrame(), None

    raw = pd.read_csv(path)
    required = {"Project_Group", "AnimalID", "Cohort", "Sex", "Genotype", "Treatment"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(
            f"Authoritative metadata file {path.name} is missing columns: "
            + ", ".join(sorted(missing))
        )
    meta = raw.rename(columns={"Project_Group": "Project", "AnimalID": "Animal_ID"})[
        ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment"]
    ].copy()
    meta = clean_meta(meta)
    meta["Project"] = meta["Project"].astype(str).str.strip()
    meta["Animal_ID"] = meta["Animal_ID"].astype(str).str.strip()
    meta = meta[(meta["Project"] != "") & (meta["Animal_ID"] != "")].copy()

    # The source file should have one row per project/animal. Fail loudly if
    # the same animal has conflicting authoritative assignments.
    key = ["Project", "Animal_ID"]
    conflicts = []
    for k, g in meta.groupby(key, dropna=False):
        for c in ["Cohort", "Sex", "Genotype", "Treatment"]:
            if g[c].dropna().astype(str).nunique() > 1:
                conflicts.append(f"{k[0]} / {k[1]} / {c}")
    if conflicts:
        raise ValueError("Conflicting authoritative metadata: " + "; ".join(conflicts[:10]))
    meta = meta.drop_duplicates(key, keep="first")
    return meta, path

def apply_authoritative_metadata(df, authoritative):
    """Overwrite graphing metadata with the source-of-truth assignments."""
    if df.empty or authoritative.empty or not {"Project", "Animal_ID"}.issubset(df.columns):
        return df
    d = df.copy()
    key = ["Project", "Animal_ID"]
    fields = ["Cohort", "Sex", "Genotype", "Treatment"]
    auth = authoritative[key + fields].copy()
    d = d.merge(auth, on=key, how="left", suffixes=("", "_auth"))
    for c in fields:
        ac = c + "_auth"
        if ac in d.columns:
            valid = d[ac].notna() & d[ac].astype(str).str.strip().ne("")
            d.loc[valid, c] = d.loc[valid, ac]
            d = d.drop(columns=[ac])
    return clean_meta(d)

def sem(vals):
    s = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if len(s) < 2:
        return 0.0
    return float(s.std(ddof=1) / np.sqrt(len(s)))

def stars(p):
    if pd.isna(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""

def project_controls(project):
    return ("PBS", "Lecanemab") if project == "Lecanemab" else ("Sham", "Vaccine")

def group_color_map(project):
    if project == "Lecanemab":
        colors = {
            ("KI2TA-3", "PBS"): "#BCEFE4",
            ("KI2TA-3", "Lecanemab"): "#63D9BE",
            ("KI2TA-4", "PBS"): "#D9C2F4",
            ("KI2TA-4", "Lecanemab"): "#B58BE8",
        }
    else:
        colors = {
            ("KI2TA-3", "Sham"): "#BFE6BF",
            ("KI2TA-3", "Vaccine"): "#59A14F",
            ("KI2TA-4", "Sham"): "#F4B6B8",
            ("KI2TA-4", "Vaccine"): "#E15759",
        }
    return {g: colors[g] for g in GROUP_ORDER[project]}


def group_style_map(project):
    control, treated = project_controls(project)
    cmap = group_color_map(project)
    return {
        g: {
            "color": cmap[g],
            "linestyle": "-" if g[1] == treated else ":",
            "linewidth": 2.5 if g[1] == treated else 2.2,
        }
        for g in GROUP_ORDER[project]
    }

def metric_values(series, percent):
    s = pd.to_numeric(series, errors="coerce")
    return s * 100.0 if percent else s

def dur_label(dur):
    return f"{dur:g}s"

def percent_change(followup, baseline):
    base = pd.to_numeric(baseline, errors="coerce")
    foll = pd.to_numeric(followup, errors="coerce")
    denom = base.abs().replace(0, np.nan)
    return ((foll - base) / denom * 100.0).replace([np.inf, -np.inf], np.nan)

def apply_change_ylim(ax, vals):
    s = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if s.empty:
        ax.set_ylim(-10, 10)
        return
    lo, hi = np.nanpercentile(s, [2, 98])
    m = max(abs(lo), abs(hi), 10)
    ax.set_ylim(-m * 1.18, m * 1.18)

def apply_iti_delta_ylim(ax, vals):
    s = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if s.empty:
        ax.set_ylim(-0.25, 0.25)
        return
    lo, hi = np.nanpercentile(s, [2, 98])
    m = max(abs(lo), abs(hi), 0.15)
    ax.set_ylim(-m * 1.35, m * 1.35)

def group_n(df, geno, trt):
    return int(df.loc[(df["Genotype"] == geno) & (df["Treatment"] == trt), "Animal_ID"].nunique())

def n_footer(df, project):
    bits = []
    for geno, trt in GROUP_ORDER[project]:
        n = group_n(df, geno, trt)
        if n:
            bits.append(f"{geno} | {trt}: n={n}")
    return "   |   ".join(bits)

def apply_smart_ylim(ax, vals, percent=False):
    s = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if s.empty:
        return
    lo, hi = float(s.min()), float(s.max())
    if percent:
        pad = max(3.0, 0.14 * max(hi - lo, 10))
        ax.set_ylim(max(0, lo - pad), min(100, hi + pad))
    else:
        span = max(hi - lo, abs(hi) * 0.08, 0.05)
        ax.set_ylim(lo - 0.18 * span, hi + 0.25 * span)

def contrast_star(contrasts, project, outcome, sex, geno, tp, dur):
    if contrasts.empty:
        return ""
    q = contrasts[
        (contrasts["Project"].astype(str) == project) &
        (contrasts["Outcome"].astype(str) == outcome) &
        (contrasts["Sex"].astype(str) == sex) &
        (contrasts["Genotype"].astype(str) == geno) &
        (pd.to_numeric(contrasts["Timepoint_Months"], errors="coerce") == tp) &
        np.isclose(pd.to_numeric(contrasts["Stimulus_Duration_s"], errors="coerce"), dur, equal_nan=False)
    ]
    if q.empty:
        return ""
    p = pd.to_numeric(q.iloc[0].get("p_Holm_within_Project_Outcome"), errors="coerce")
    return stars(p)


def contrast_pvalue(contrasts, project, outcome, sex, geno, tp, dur):
    if contrasts.empty:
        return np.nan
    q = contrasts[
        (contrasts["Project"].astype(str) == project) &
        (contrasts["Outcome"].astype(str) == outcome) &
        (contrasts["Sex"].astype(str) == sex) &
        (contrasts["Genotype"].astype(str) == geno) &
        (pd.to_numeric(contrasts["Timepoint_Months"], errors="coerce") == tp) &
        np.isclose(pd.to_numeric(contrasts["Stimulus_Duration_s"], errors="coerce"), dur, equal_nan=False)
    ]
    if q.empty:
        return np.nan
    return pd.to_numeric(q.iloc[0].get("p_Holm_within_Project_Outcome"), errors="coerce")

def add_sig_bracket(ax, x1, x2, y, p, color="black"):
    if pd.isna(p) or p >= 0.05:
        return
    yr = ax.get_ylim()
    span = max(yr[1] - yr[0], 1e-6)
    h = span * 0.025
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=1.0, color=color, clip_on=False)
    st = stars(p)
    ptxt = f"{st}  p_adj={p:.3g}"
    ax.text((x1 + x2) / 2, y + h * 1.18, ptxt, ha="center", va="bottom",
            fontsize=7.5, fontweight="bold", color=color)

def legend_bottom(fig, handles, labels, ncol=2, y=0.02, fontsize=8.5):
    if handles:
        fig.legend(
            handles, labels,
            loc="lower center",
            bbox_to_anchor=(0.5, y),
            ncol=ncol,
            frameon=False,
            fontsize=fontsize,
            columnspacing=1.8,
            handlelength=2.6,
        )

def sex_n_label(df, geno, trt):
    gd = df[(df["Genotype"] == geno) & (df["Treatment"] == trt)]
    nf = gd.loc[gd["Sex"] == "Female", "Animal_ID"].astype(str).nunique()
    nm = gd.loc[gd["Sex"] == "Male", "Animal_ID"].astype(str).nunique()
    return f"{geno} | {trt} (Female n={nf}; Male n={nm})"

def combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5):
    styles = group_style_map(project)
    handles, labels = [], []
    for geno, trt in GROUP_ORDER[project]:
        gd = count_df[(count_df["Genotype"] == geno) & (count_df["Treatment"] == trt)]
        if gd.empty:
            continue
        st = styles[(geno, trt)]
        handles.append(plt.Line2D([0], [0], color=st["color"],
                                  linestyle=st["linestyle"], linewidth=st["linewidth"],
                                  marker="o", markersize=5))
        labels.append(sex_n_label(count_df, geno, trt))
    legend_bottom(fig, handles, labels, ncol=2, y=y, fontsize=fontsize)

def add_sex_watermark(ax, sex):
    if sex not in {"Female", "Male"}:
        return
    color = "#FF2D9A" if sex == "Female" else "#006CFF"
    ax.text(
        .96, .88, sex,
        transform=ax.transAxes,
        ha="right", va="top",
        fontsize=18, fontweight="bold",
        color=color, alpha=.16,
        zorder=0
    )

def tight_category_positions(n):
    """Return compact x positions for grouped bar categories."""
    if n == 2:
        return np.array([0.0, 0.72], dtype=float)
    return np.arange(n, dtype=float)

def apply_tight_category_axis(ax, positions):
    if len(positions) == 2:
        ax.set_xlim(positions[0] - .46, positions[-1] + .46)

def sync_y_limits(ax_list):
    live_axes = [ax for ax in ax_list if ax.has_data()]
    if not live_axes:
        return
    lows, highs = zip(*(ax.get_ylim() for ax in live_axes))
    lo, hi = min(lows), max(highs)
    for ax in live_axes:
        ax.set_ylim(lo, hi)

def title_page(pdf, project, animal, authoritative=None):
    fig = plt.figure(figsize=(13.333, 7.5))
    d = animal[animal["Project"].eq(project)].copy()
    count_source = d
    n = count_source["Animal_ID"].astype(str).nunique()
    fig.text(.5, .70, f"{project} CPT Story", ha="center", fontsize=30, fontweight="bold")
    fig.text(.5, .60, "Atlas QC-approved analysis -> statistics -> presentation graphs", ha="center", fontsize=15)
    fig.text(.5, .52, f"{n} animals represented in the analysis-ready dataset", ha="center", fontsize=13)

    # Display corrected group n values and sex breakdowns on the opening slide.
    # Counts are unique animals, not session rows.
    group_lines = []
    for geno, trt in GROUP_ORDER.get(project, []):
        gd = count_source[(count_source["Genotype"] == geno) & (count_source["Treatment"] == trt)]
        ids = gd["Animal_ID"].astype(str).unique()
        nf = gd.loc[gd["Sex"] == "Female", "Animal_ID"].astype(str).nunique()
        nm = gd.loc[gd["Sex"] == "Male", "Animal_ID"].astype(str).nunique()
        group_lines.append(f"{geno} | {trt}: n={len(ids)}  (Female n={nf}; Male n={nm})")
    fig.text(.5, .38, "\n".join(group_lines), ha="center", va="center", fontsize=12,
             linespacing=1.45)
    fig.text(
        .5, .17,
        "Main story is organized by time point, then sex.\n"
        "Each main graph contains one sex only.",
        ha="center", fontsize=12
    )
    source_note = "Opening-slide n values: analysis-ready plotted dataset; metadata only corrects group labels"
    fig.text(.5, .075, source_note, ha="center", fontsize=8.5, color="0.35")
    fig.text(.5, .04, f"ATLAS CPT Graph Maker v{VERSION}", ha="center", fontsize=9)
    pdf.savefig(fig)
    plt.close(fig)

def divider_page(pdf, project, tp):
    fig = plt.figure(figsize=(13.333, 7.5))
    fig.text(.5, .60, f"{project}", ha="center", fontsize=24, fontweight="bold")
    fig.text(.5, .46, f"{tp} months", ha="center", fontsize=36, fontweight="bold")
    fig.text(.5, .30, "Female and male results are shown separately.", ha="center", fontsize=13)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def timepoint_title_page(pdf, project, tp, animal, authoritative=None):
    fig = plt.figure(figsize=(13.333, 7.5))
    d = animal[(animal["Project"].eq(project)) & (animal["Timepoint_Months"].eq(tp))].copy()
    fig.text(.5, .68, f"{project}", ha="center", fontsize=28, fontweight="bold")
    fig.text(.5, .55, f"{tp} months", ha="center", fontsize=38, fontweight="bold")
    fig.text(.5, .44, "Stage 4 baseline to Probe 2b: main measures and latencies",
             ha="center", fontsize=14)
    group_lines = []
    count_source = d
    for geno, trt in GROUP_ORDER.get(project, []):
        gd = count_source[(count_source["Genotype"] == geno) & (count_source["Treatment"] == trt)]
        nf = gd.loc[gd["Sex"] == "Female", "Animal_ID"].astype(str).nunique()
        nm = gd.loc[gd["Sex"] == "Male", "Animal_ID"].astype(str).nunique()
        n = gd["Animal_ID"].astype(str).nunique()
        group_lines.append(f"{geno} | {trt}: n={n}  (Female n={nf}; Male n={nm})")
    fig.text(.5, .29, "\n".join(group_lines), ha="center", va="center", fontsize=11.5,
             linespacing=1.4)
    fig.text(.5, .08, f"ATLAS CPT Graph Maker v{VERSION}", ha="center", fontsize=9)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def comparison_title_page(pdf, project, animal, authoritative=None):
    fig = plt.figure(figsize=(13.333, 7.5))
    d = animal[animal["Project"].eq(project)].copy()
    count_source = d
    n = count_source["Animal_ID"].astype(str).nunique()
    fig.text(.5, .66, f"{project}", ha="center", fontsize=28, fontweight="bold")
    fig.text(.5, .52, "6 / 9 / 12 month comparison", ha="center", fontsize=34, fontweight="bold")
    fig.text(.5, .40, f"{n} animals represented in the analysis-ready plotted dataset",
             ha="center", fontsize=13)
    fig.text(.5, .28,
             "Female panels are shown on the left and male panels on the right.\n"
             "Main measures and selected latencies are summarized across 6, 9 and 12 months by stimulus duration.",
             ha="center", fontsize=12)
    fig.text(.5, .08, f"ATLAS CPT Graph Maker v{VERSION}", ha="center", fontsize=9)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def animal_ids_page(pdf, project, animal):
    d = animal[animal["Project"].eq(project)].copy()
    fig, ax = plt.subplots(figsize=(13.333, 7.5))
    ax.axis("off")
    fig.suptitle(f"{project}: animal IDs by group", fontsize=20, fontweight="bold", y=.96)
    y = .88
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        ids = sorted(gd["Animal_ID"].astype(str).unique())
        if not ids:
            continue
        ax.text(.03, y, f"{geno} | {trt} (n={len(ids)})", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="top")
        y -= .035
        line = ""
        lines = []
        for ident in ids:
            candidate = ident if not line else line + ", " + ident
            if len(candidate) > 125:
                lines.append(line)
                line = ident
            else:
                line = candidate
        if line:
            lines.append(line)
        for ln in lines[:5]:
            ax.text(.05, y, ln, transform=ax.transAxes, fontsize=8.2, va="top")
            y -= .027
        if len(lines) > 5:
            ax.text(.05, y, "[additional IDs remain in the analysis CSV]", transform=ax.transAxes, fontsize=8)
            y -= .03
        y -= .025
        if y < .08:
            break
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def timepoint_sex_comparison_page(pdf, project, tp, animal):
    d = animal[(animal["Project"] == project) & (animal["Timepoint_Months"] == tp)].copy()
    if d.empty:
        return
    sex_colors = {"Female": "#FF2D5F", "Male": "#1683F7"}
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months: descriptive sex comparison",
                 fontsize=20, fontweight="bold", y=.985)
    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        means, errors, vals_all = [], [], []
        for xi, sex in enumerate(SEXES):
            ad = d[d["Sex"] == sex].groupby("Animal_ID", as_index=False)[col].mean()
            s = metric_values(ad[col], percent).dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            if not s.empty:
                jitter = np.linspace(-.04, .04, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), xi) + jitter, s, s=16,
                           color=sex_colors.get(sex, "0.5"), edgecolors="white",
                           linewidths=.35, zorder=4)
                vals_all.extend(s.tolist())
        ax.bar(range(len(SEXES)), means, width=.52, color=[sex_colors[s] for s in SEXES],
               alpha=.45, edgecolor="0.35", linewidth=.65, zorder=2)
        ax.errorbar(range(len(SEXES)), means, yerr=errors, fmt="none",
                    ecolor="0.20", elinewidth=1.05, capsize=3, capthick=1.05, zorder=7)
        ax.set_xticks(range(len(SEXES)))
        ax.set_xticklabels(SEXES)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, vals_all, percent)
    axes.flat[7].axis("off")
    fig.text(.5, .045,
             "Descriptive only: genotype, treatment and stimulus duration are collapsed within this time point.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .08, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def timepoint_genotype_comparison_page(pdf, project, tp, animal):
    d = animal[(animal["Project"] == project) & (animal["Timepoint_Months"] == tp)].copy()
    if d.empty:
        return
    geno_colors = {"KI2TA-3": "#63D9BE" if project == "Lecanemab" else "#59A14F",
                   "KI2TA-4": "#B58BE8" if project == "Lecanemab" else "#E15759"}
    genos = ["KI2TA-3", "KI2TA-4"]
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months: descriptive strain/genotype comparison",
                 fontsize=20, fontweight="bold", y=.985)
    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        means, errors, vals_all = [], [], []
        for xi, geno in enumerate(genos):
            ad = d[d["Genotype"] == geno].groupby("Animal_ID", as_index=False)[col].mean()
            s = metric_values(ad[col], percent).dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            if not s.empty:
                jitter = np.linspace(-.04, .04, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), xi) + jitter, s, s=16,
                           color=geno_colors.get(geno, "0.5"), edgecolors="white",
                           linewidths=.35, zorder=4)
                vals_all.extend(s.tolist())
        ax.bar(range(len(genos)), means, width=.52, color=[geno_colors[g] for g in genos],
               alpha=.45, edgecolor="0.35", linewidth=.65, zorder=2)
        ax.errorbar(range(len(genos)), means, yerr=errors, fmt="none",
                    ecolor="0.20", elinewidth=1.05, capsize=3, capthick=1.05, zorder=7)
        ax.set_xticks(range(len(genos)))
        ax.set_xticklabels(genos)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, vals_all, percent)
    axes.flat[7].axis("off")
    fig.text(.5, .045,
             "Descriptive only: sex, treatment and stimulus duration are collapsed within this time point.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .08, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def whole_session_line_page(pdf, project, tp, sex, animal, contrasts):
    # Explanatory subtitles used by the whole-session Probe 2b profile.
    # This dictionary must be local/global here; previously it only existed
    # inside the correction-trial plotting function, which caused a NameError
    # immediately after the title/divider page was written.
    metric_explanations = {
        "Hit_Rate": "Signal trials: proportion of targets correctly detected.",
        "False_Alarm_Rate": "Non-target trials: proportion incorrectly responded to.",
        "d_prime": "Signal-detection sensitivity; higher values indicate better target/non-target discrimination.",
        "criterion_c": "Response criterion; positive values indicate a more conservative response tendency.",
        "Mean_Session_Correct_Touch_Latency_s": "Mean latency for correct target responses.",
        "Mean_Session_Incorrect_Touch_Latency_s": "Mean latency for incorrect non-target responses.",
        "Mean_Session_Reward_Retrieval_Latency_s": "Mean latency to collect reward following a rewarded response.",
    }

    d = animal[
        (animal["Project"] == project) &
        (animal["Timepoint_Months"] == tp) &
        (animal["Sex"] == sex)
    ].copy()
    if d.empty:
        return
    styles = group_style_map(project)
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: Probe 2b stimulus-duration profile",
                 fontsize=20, fontweight="bold", y=.985)
    legend_handles = legend_labels = None

    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        allvals = []
        for geno, trt in GROUP_ORDER[project]:
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd.empty:
                continue
            xs, ys, es = [], [], []
            for j, dur in enumerate(DURS):
                s = metric_values(gd.loc[np.isclose(gd["Stimulus_Duration_s"], dur), col], percent).dropna()
                if s.empty:
                    continue
                xs.append(j); ys.append(float(s.mean())); es.append(sem(s))
            if not xs:
                continue
            st = styles[(geno, trt)]
            n = gd["Animal_ID"].nunique()
            ax.errorbar(xs, ys, yerr=es, marker="o", markersize=5, capsize=3,
                        color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                        label=f"{geno} | {trt} (n={n})")
            allvals.extend(np.array(ys) + np.array(es))
            allvals.extend(np.array(ys) - np.array(es))
            if trt == project_controls(project)[1]:
                model_outcome = COL_TO_MODEL_OUTCOME[col]
                for x, dur, y, e in zip(xs, [DURS[x] for x in xs], ys, es):
                    stxt = contrast_star(contrasts, project, model_outcome, sex, geno, tp, dur)
                    if stxt:
                        ax.annotate(stxt, (x, y + e), xytext=(0, 7), textcoords="offset points",
                                    ha="center", fontsize=11, fontweight="bold", color=st["color"])
        ax.set_xticks(range(4))
        ax.set_xticklabels(["2.0", "1.0", "0.5", "0.2"])
        ax.set_xlabel("Stimulus duration (s)", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        expl = metric_explanations.get(col, "")
        if expl:
            ax.text(.5, 1.12, expl,
                    transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=7.1, color="0.28", wrap=True)
        add_sex_watermark(ax, sex)
        ax.grid(alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)
        if legend_handles is None:
            legend_handles, legend_labels = ax.get_legend_handles_labels()

    axes.flat[7].axis("off")
    count_df = animal[
        (animal["Project"] == project) &
        (animal["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.045, fontsize=8.6)
    fig.text(.5, .012, "Solid = treated; dotted = control. Holm-adjusted planned treatment contrasts: * p<0.05, ** p<0.01, *** p<0.001.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_whole_session_metric(ax, project, tp, sex, animal, contrasts, col, label, percent):
    metric_col = _resolve_metric_column(animal, col)
    if metric_col is None:
        ax.axis("off")
        return
    d = animal[
        (animal["Project"] == project) &
        (animal["Timepoint_Months"] == tp) &
        (animal["Sex"] == sex)
    ].copy()
    if d.empty:
        ax.axis("off")
        return
    styles = group_style_map(project)
    allvals = []
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty:
            continue
        xs, ys, es = [], [], []
        for j, dur in enumerate(DURS):
            s = metric_values(gd.loc[np.isclose(gd["Stimulus_Duration_s"], dur), metric_col], percent).dropna()
            if s.empty:
                continue
            xs.append(j); ys.append(float(s.mean())); es.append(sem(s))
        if not xs:
            continue
        st = styles[(geno, trt)]
        ax.errorbar(xs, ys, yerr=es, marker="o", markersize=5, capsize=3,
                    color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                    label=f"{geno} | {trt}")
        allvals.extend((np.array(ys) + np.array(es)).tolist())
        allvals.extend((np.array(ys) - np.array(es)).tolist())
        if trt == project_controls(project)[1]:
            model_outcome = COL_TO_MODEL_OUTCOME[col]
            for x, dur, y, e in zip(xs, [DURS[x] for x in xs], ys, es):
                stxt = contrast_star(contrasts, project, model_outcome, sex, geno, tp, dur)
                if stxt:
                    ax.annotate(stxt, (x, y + e), xytext=(0, 7), textcoords="offset points",
                                ha="center", fontsize=10, fontweight="bold", color=st["color"])
    ax.set_xticks(range(4))
    ax.set_xticklabels(["2.0", "1.0", "0.5", "0.2"])
    ax.set_xlabel("Stimulus duration (s)", fontsize=8)
    ax.set_ylabel(label, fontsize=8)
    ax.set_title(f"{sex}: {label}", fontsize=10, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(alpha=.20)
    ax.tick_params(labelsize=8)
    apply_smart_ylim(ax, allvals, percent)


def whole_session_sex_comparison_pages(pdf, project, tp, animal, contrasts, title_suffix=""):
    metric_chunks = [METRICS[i:i + 2] for i in range(0, len(METRICS), 2)]
    for metric_chunk in metric_chunks:
        fig, axes = plt.subplots(len(metric_chunk), 2, figsize=(16, 9), squeeze=False)
        suffix = f" - {title_suffix}" if title_suffix else ""
        labels = " and ".join(label for _, label, _ in metric_chunk)
        fig.suptitle(
            f"{project} - {tp} months: Probe 2b whole-session stimulus-duration profile{suffix} - {labels}",
            fontsize=17.5, fontweight="bold", y=.985
        )
        plotted_axes = []
        for row_i, (col, label, percent) in enumerate(metric_chunk):
            for col_i, sex in enumerate(SEXES):
                ax = axes[row_i, col_i]
                _plot_whole_session_metric(ax, project, tp, sex, animal, contrasts, col, label, percent)
                plotted_axes.append(ax)
        sync_y_limits(plotted_axes)
        count_df = animal[
            (animal["Project"] == project) &
            (animal["Timepoint_Months"] == tp)
        ].copy()
        combined_group_legend(fig, project, count_df, y=.047, fontsize=8.4)
        fig.text(.5, .012,
                 "Female panels are on the left; male panels are on the right. "
                 "Y-axis is matched across sex panels within each measure.",
                 ha="center", fontsize=8.1)
        fig.tight_layout(rect=[.02, .16, .98, .93])
        pdf.savefig(fig)
        plt.close(fig)


def bar_dot_page(pdf, project, tp, sex, animal, contrasts):
    d = animal[
        (animal["Project"] == project) &
        (animal["Timepoint_Months"] == tp) &
        (animal["Sex"] == sex)
    ].copy()
    if d.empty:
        return
    colors = group_color_map(project)
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: individual-animal Probe 2b values",
                 fontsize=20, fontweight="bold", y=.985)

    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    width = .16
    offsets = np.linspace(-.27, .27, max(1, len(group_present)))
    offset_map = {g: offsets[i] for i, g in enumerate(group_present)}

    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        allvals = []
        tops = {}
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            xpos = np.arange(4, dtype=float) + offsets[gi]
            means, errors = [], []

            for di, dur in enumerate(DURS):
                cell = gd[np.isclose(gd["Stimulus_Duration_s"], dur)]
                s = metric_values(cell[col], percent).dropna()
                means.append(float(s.mean()) if not s.empty else np.nan)
                errors.append(sem(s))
                if not s.empty:
                    animal_vals = cell[["Animal_ID", col]].dropna().copy()
                    animal_vals["PlotValue"] = metric_values(animal_vals[col], percent)
                    jitter = np.linspace(-.035, .035, len(animal_vals)) if len(animal_vals) > 1 else np.array([0.0])
                    ax.scatter(
                        np.full(len(animal_vals), xpos[di]) + jitter,
                        animal_vals["PlotValue"],
                        s=14, marker="o",
                        color=colors[(geno, trt)],
                        edgecolors="white", linewidths=.35,
                        zorder=4
                    )
                    allvals.extend(animal_vals["PlotValue"].tolist())
                if np.isfinite(means[-1]):
                    top = means[-1] + errors[-1]
                    allvals += [top, means[-1] - errors[-1]]
                    tops[(geno, trt, dur)] = top

            ax.bar(
                xpos, means, width=width,
                color=colors[(geno, trt)], alpha=.58,
                edgecolor="0.35", linewidth=.65,
                label=f"{geno} | {trt} (n={gd['Animal_ID'].nunique()})",
                zorder=2
            )
            ax.errorbar(
                xpos, means, yerr=errors, fmt="none",
                ecolor="0.20", elinewidth=1.05, capsize=2.8, capthick=1.05,
                zorder=7
            )

        ax.set_xticks(range(4))
        ax.set_xticklabels(["2.0", "1.0", "0.5", "0.2"])
        ax.set_xlabel("Stimulus duration (s)", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)

        # Clearly identify significant planned treated-vs-control contrasts.
        control, treated = project_controls(project)
        for geno in ["KI2TA-3", "KI2TA-4"]:
            gc = (geno, control)
            gt = (geno, treated)
            if gc not in offset_map or gt not in offset_map:
                continue
            for di, dur in enumerate(DURS):
                p = contrast_pvalue(contrasts, project, COL_TO_MODEL_OUTCOME[col], sex, geno, tp, dur)
                if pd.isna(p) or p >= 0.05:
                    continue
                if (geno, control, dur) not in tops or (geno, treated, dur) not in tops:
                    continue
                ymin, ymax = ax.get_ylim()
                span = ymax - ymin
                y = max(tops[(geno, control, dur)], tops[(geno, treated, dur)]) + span * .035
                # expand ylim if bracket needs room
                if y + span*.08 > ymax:
                    ax.set_ylim(ymin, y + span*.11)
                x1 = di + offset_map[gc]
                x2 = di + offset_map[gt]
                add_sig_bracket(ax, x1, x2, y, p, color=colors[gt])

    axes.flat[7].axis("off")
    count_df = animal[
        (animal["Project"] == project) &
        (animal["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.6)
    fig.text(.5, .012,
             "Each dot = one mouse; dot color matches its group. Bars = mean +/- SEM. Significant brackets show the Holm-adjusted treated-vs-control contrast.",
             ha="center", fontsize=8.2)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def first_last_page(pdf, project, tp, sex, session):
    d = session[
        (session["Project"] == project) &
        (session["Timepoint_Months"] == tp) &
        (session["Sex"] == sex) &
        (session["Probe_Session_Number"].isin([1, 2, 3, 4]))
    ].copy()
    if d.empty:
        return
    d["Probe_Block"] = np.where(
        pd.to_numeric(d["Probe_Session_Number"], errors="coerce").isin([1, 2]),
        "Early sessions 1-2",
        "Late sessions 3-4",
    )
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    width = .26
    block_offsets = {"Early sessions 1-2": -width / 2, "Late sessions 3-4": width / 2}
    cats = ["Early sessions 1-2", "Late sessions 3-4"]
    centers = np.arange(len(group_present), dtype=float)

    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: early vs late Probe 2b sessions",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (animal_col, label, percent) in enumerate(METRICS):
        session_col = {
            "Mean_Session_Correct_Touch_Latency_s": "Mean_Correct_Touch_Latency_s",
            "Mean_Session_Incorrect_Touch_Latency_s": "Mean_Incorrect_Touch_Latency_s",
            "Mean_Session_Reward_Retrieval_Latency_s": "Mean_Reward_Retrieval_Latency_s",
        }.get(animal_col, animal_col)
        if session_col not in d.columns:
            axes.flat[i].axis("off")
            continue
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd.empty:
                continue
            # Average stimulus durations and sessions inside each early/late block.
            av = gd.groupby(["Animal_ID", "Probe_Block"], as_index=False)[session_col].mean()
            means, errors = [], []
            for ci, cat in enumerate(cats):
                s = metric_values(av.loc[av["Probe_Block"] == cat, session_col], percent).dropna()
                means.append(float(s.mean()) if not s.empty else np.nan)
                errors.append(sem(s))
                if s.empty:
                    continue
                jitter = np.linspace(-.03, .03, len(s)) if len(s) > 1 else np.array([0.0])
                xpos = centers[gi] + block_offsets[cat]
                ax.scatter(np.full(len(s), xpos) + jitter, s, s=15,
                           color=colors[(geno, trt)], edgecolors="white",
                           linewidths=.35, zorder=4)
                allvals.extend(s.tolist())
                if np.isfinite(means[-1]):
                    allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]
            xpos = np.array([centers[gi] + block_offsets[cat] for cat in cats])
            ax.bar(xpos, means, width=width, color=colors[(geno, trt)], alpha=.58,
                   edgecolor="0.35", linewidth=.65,
                   label=f"{geno} | {trt} (n={av['Animal_ID'].nunique()})",
                   zorder=2)
            ax.errorbar(xpos, means, yerr=errors, fmt="none", ecolor="0.20",
                        elinewidth=1.05, capsize=2.8, capthick=1.05, zorder=7)
            if all(np.isfinite(means)):
                ax.plot(xpos, means, color="0.25", linewidth=.85, alpha=.65, zorder=6)
        ax.set_xticks(centers)
        ax.set_xticklabels([f"{g}\n{t}" for g, t in group_present], fontsize=7)
        ax.set_xlabel("Group (left bar = early sessions 1-2; right bar = late sessions 3-4)", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)

    axes.flat[7].axis("off")
    count_df = session[
        (session["Project"] == project) &
        (session["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012, "Within each group, left bar = early sessions 1-2 and right bar = late sessions 3-4. Thin grey line connects group means.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def first_last_percent_change_page(pdf, project, tp, sex, session):
    d = session[
        (session["Project"] == project) &
        (session["Timepoint_Months"] == tp) &
        (session["Sex"] == sex) &
        (session["Probe_Session_Number"].isin([1, 2, 3, 4]))
    ].copy()
    if d.empty:
        return
    d["Probe_Block"] = np.where(
        pd.to_numeric(d["Probe_Session_Number"], errors="coerce").isin([1, 2]),
        "Early sessions 1-2",
        "Late sessions 3-4",
    )
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    centers = np.arange(len(group_present), dtype=float)

    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: % change from early to late Probe 2b sessions",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (animal_col, label, percent) in enumerate(METRICS):
        session_col = {
            "Mean_Session_Correct_Touch_Latency_s": "Mean_Correct_Touch_Latency_s",
            "Mean_Session_Incorrect_Touch_Latency_s": "Mean_Incorrect_Touch_Latency_s",
            "Mean_Session_Reward_Retrieval_Latency_s": "Mean_Reward_Retrieval_Latency_s",
        }.get(animal_col, animal_col)
        if session_col not in d.columns:
            axes.flat[i].axis("off")
            continue
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd.empty:
                continue
            av = gd.groupby(["Animal_ID", "Probe_Block"], as_index=False)[session_col].mean()
            wide = av.pivot(index="Animal_ID", columns="Probe_Block", values=session_col)
            if not {"Early sessions 1-2", "Late sessions 3-4"}.issubset(wide.columns):
                continue
            base = metric_values(wide["Early sessions 1-2"], percent)
            follow = metric_values(wide["Late sessions 3-4"], percent)
            s = percent_change(follow, base).dropna()
            if s.empty:
                continue
            mean, err = float(s.mean()), sem(s)
            ax.bar([centers[gi]], [mean], yerr=[err], width=.52, capsize=3,
                   color=colors[(geno, trt)], alpha=.60, edgecolor="0.35",
                   linewidth=.65, label=f"{geno} | {trt} (n={len(s)})", zorder=2)
            jitter = np.linspace(-.055, .055, len(s)) if len(s) > 1 else np.array([0.0])
            ax.scatter(np.full(len(s), centers[gi]) + jitter, s, s=17,
                       color=colors[(geno, trt)], edgecolors="white",
                       linewidths=.35, zorder=4)
            allvals.extend(s.tolist())
            allvals.extend([mean + err, mean - err])
        ax.axhline(0, color="0.15", linewidth=1.1, alpha=.85)
        ax.set_xticks(centers)
        ax.set_xticklabels([f"{g}\n{t}" for g, t in group_present], fontsize=7)
        ax.set_ylabel("% change", fontsize=8)
        ax.set_title(f"{label}: late vs early", fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_change_ylim(ax, allvals)

    axes.flat[7].axis("off")
    count_df = session[
        (session["Project"] == project) &
        (session["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Zero line = no change. Percent change is calculated per mouse: (late sessions 3-4 - early sessions 1-2) / early sessions 1-2 x 100.",
             ha="center", fontsize=8.4)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def compute_trial_bins(trial):
    if trial.empty or "Session_Progress_Decile" not in trial.columns:
        return pd.DataFrame()
    d = trial.copy()
    if "Analysis_Eligible" in d.columns:
        d = d[d["Analysis_Eligible"].astype(bool)]
    if "Core_Trial" in d.columns:
        d = d[pd.to_numeric(d["Core_Trial"], errors="coerce").fillna(0).eq(1)]
    for c in ["Hit", "Miss", "False_Alarm", "Correct_Rejection"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["Session_Half"] = np.where(
        pd.to_numeric(d["Session_Progress_Decile"], errors="coerce").le(5),
        "First half",
        "Last half",
    )

    grp = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s", "Session_Half"]
    rows = []
    from scipy.stats import norm
    for key, g in d.groupby(grp, dropna=False):
        r = dict(zip(grp, key))
        h, m, fa, cr = [float(g[c].sum()) for c in ["Hit", "Miss", "False_Alarm", "Correct_Rejection"]]
        r["Hit_Rate"] = h / (h + m) if h + m else np.nan
        r["False_Alarm_Rate"] = fa / (fa + cr) if fa + cr else np.nan
        if h + m and fa + cr:
            hr = (h + .5) / (h + m + 1)
            fr = (fa + .5) / (fa + cr + 1)
            r["d_prime"] = norm.ppf(hr) - norm.ppf(fr)
            r["criterion_c"] = -.5 * (norm.ppf(hr) + norm.ppf(fr))
        else:
            r["d_prime"] = np.nan
            r["criterion_c"] = np.nan
        for raw, out in [
            ("Correct_Touch_Latency_AnalysisClean_s", "Mean_Session_Correct_Touch_Latency_s"),
            ("Incorrect_Touch_Latency_AnalysisClean_s", "Mean_Session_Incorrect_Touch_Latency_s"),
            ("Reward_Retrieval_Latency_AnalysisClean_s", "Mean_Session_Reward_Retrieval_Latency_s"),
        ]:
            r[out] = pd.to_numeric(g.get(raw), errors="coerce").mean()
        rows.append(r)
    return pd.DataFrame(rows)

def make_decile_animal_metrics(trial):
    """Build one row per mouse x timepoint x SD x session-progress decile.

    Standard CPT performance is calculated from non-correction trials only.
    Correction-trial rows remain available to the separate correction-trial analysis.
    """
    if trial.empty or "Session_Progress_Decile" not in trial.columns:
        return pd.DataFrame()
    d = trial.copy()

    # Keep Atlas/QC eligible rows when the flags exist.
    if "Analysis_Eligible" in d.columns:
        flag = d["Analysis_Eligible"]
        if flag.dtype == bool:
            d = d[flag]
        else:
            d = d[flag.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y"])]

    # Explicitly exclude correction trials from ordinary CPT HR/FAR/d-prime/c.
    corr_cols = [c for c in ["Correction_Trial_Correct_Rejection", "Correction_Trial_Mistake"] if c in d.columns]
    if corr_cols:
        corr_mask = pd.Series(False, index=d.index)
        for c in corr_cols:
            corr_mask |= pd.to_numeric(d[c], errors="coerce").fillna(0).gt(0)
        d = d[~corr_mask].copy()
    elif "Outcome" in d.columns:
        d = d[~d["Outcome"].astype(str).str.contains("Correction Trial", case=False, na=False)].copy()

    needed = ["Project", "Animal_ID", "Sex", "Genotype", "Treatment",
              "Timepoint_Months", "Stimulus_Duration_s", "Session_Progress_Decile"]
    if any(c not in d.columns for c in needed):
        return pd.DataFrame()
    if "Cohort" not in d.columns:
        d["Cohort"] = ""
    if "Probe_Session_Number" not in d.columns:
        d["Probe_Session_Number"] = np.nan

    for c in ["Hit", "Miss", "False_Alarm", "Correct_Rejection"]:
        if c not in d.columns:
            d[c] = 0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    correct_lat = first_present(d, [
        "Correct_Touch_Latency_AnalysisClean_s", "Correct_Touch_Latency_IQRclean_s",
        "Correct_Touch_Latency_s", "Correct_Touch_Latency_Raw_s"
    ])
    reward_lat = first_present(d, [
        "Reward_Retrieval_Latency_AnalysisClean_s", "Reward_Retrieval_Latency_IQRclean_s",
        "Reward_Retrieval_Latency_s", "Reward_Retrieval_Latency_Raw_s"
    ])

    grp = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s", "Session_Progress_Decile"]
    rows = []
    from scipy.stats import norm
    for key, g in d.groupby(grp, dropna=False):
        r = dict(zip(grp, key))
        h = float(g["Hit"].sum()); m = float(g["Miss"].sum())
        fa = float(g["False_Alarm"].sum()); cr = float(g["Correct_Rejection"].sum())
        r["N_Standard_Trials"] = int(len(g))
        r["Hit_Rate"] = h / (h + m) if (h + m) else np.nan
        r["False_Alarm_Rate"] = fa / (fa + cr) if (fa + cr) else np.nan
        if (h + m) and (fa + cr):
            # Log-linear correction avoids +/- infinity at 0% and 100%.
            hr = (h + .5) / (h + m + 1)
            fr = (fa + .5) / (fa + cr + 1)
            r["d_prime"] = norm.ppf(hr) - norm.ppf(fr)
            r["criterion_c"] = -.5 * (norm.ppf(hr) + norm.ppf(fr))
        else:
            r["d_prime"] = np.nan
            r["criterion_c"] = np.nan
        r["Mean_Session_Correct_Touch_Latency_s"] = (
            pd.to_numeric(g[correct_lat], errors="coerce").mean() if correct_lat else np.nan
        )
        r["Mean_Session_Reward_Retrieval_Latency_s"] = (
            pd.to_numeric(g[reward_lat], errors="coerce").mean() if reward_lat else np.nan
        )
        rows.append(r)
    return clean_meta(pd.DataFrame(rows))

def make_iti_animal_metrics(trial):
    """Animal-level CPT metrics split by stimulus duration and 2/3 s ITI.

    Values are collapsed across Probe 2b sessions 1-4 within each animal,
    time point, stimulus duration, ITI, and session half.
    """
    needed = ["Project", "Animal_ID", "Sex", "Genotype", "Treatment",
              "Timepoint_Months", "Stimulus_Duration_s", "Current_ITI_s"]
    if trial.empty or any(c not in trial.columns for c in needed):
        return pd.DataFrame()
    d = trial.copy()
    if "Analysis_Eligible" in d.columns:
        flag = d["Analysis_Eligible"]
        if flag.dtype == bool:
            d = d[flag]
        else:
            d = d[flag.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y"])]
    if "Probe_Session_Number" in d.columns:
        psn = pd.to_numeric(d["Probe_Session_Number"], errors="coerce")
        d = d[psn.isin([1, 2, 3, 4]) | psn.isna()].copy()
    else:
        d["Probe_Session_Number"] = np.nan

    corr_cols = [c for c in ["Correction_Trial_Correct_Rejection", "Correction_Trial_Mistake"] if c in d.columns]
    if corr_cols:
        corr_mask = pd.Series(False, index=d.index)
        for c in corr_cols:
            corr_mask |= pd.to_numeric(d[c], errors="coerce").fillna(0).gt(0)
        d = d[~corr_mask].copy()
    elif "Outcome" in d.columns:
        d = d[~d["Outcome"].astype(str).str.contains("Correction Trial", case=False, na=False)].copy()

    if "Cohort" not in d.columns:
        d["Cohort"] = ""
    d["Current_ITI_s"] = pd.to_numeric(d["Current_ITI_s"], errors="coerce")
    d = d[d["Current_ITI_s"].isin([2, 3])].copy()
    if d.empty:
        return pd.DataFrame()

    if "Session_Progress_Decile" in d.columns:
        d["Session_Half"] = np.where(
            pd.to_numeric(d["Session_Progress_Decile"], errors="coerce").le(5),
            "First half",
            "Last half",
        )
    else:
        d["Session_Half"] = "Whole session"

    for c in ["Hit", "Miss", "False_Alarm", "Correct_Rejection"]:
        if c not in d.columns:
            d[c] = 0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    correct_lat = first_present(d, [
        "Correct_Touch_Latency_AnalysisClean_s", "Correct_Touch_Latency_IQRclean_s",
        "Correct_Touch_Latency_s", "Correct_Touch_Latency_Raw_s"
    ])
    reward_lat = first_present(d, [
        "Reward_Retrieval_Latency_AnalysisClean_s", "Reward_Retrieval_Latency_IQRclean_s",
        "Reward_Retrieval_Latency_s", "Reward_Retrieval_Latency_Raw_s"
    ])

    grp = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s", "Current_ITI_s", "Session_Half"]
    rows = []
    from scipy.stats import norm
    for key, g in d.groupby(grp, dropna=False):
        r = dict(zip(grp, key))
        h = float(g["Hit"].sum()); m = float(g["Miss"].sum())
        fa = float(g["False_Alarm"].sum()); cr = float(g["Correct_Rejection"].sum())
        r["N_Trials"] = int(len(g))
        r["Hit_Rate"] = h / (h + m) if (h + m) else np.nan
        r["False_Alarm_Rate"] = fa / (fa + cr) if (fa + cr) else np.nan
        if (h + m) and (fa + cr):
            hr = (h + .5) / (h + m + 1)
            fr = (fa + .5) / (fa + cr + 1)
            r["d_prime"] = norm.ppf(hr) - norm.ppf(fr)
            r["criterion_c"] = -.5 * (norm.ppf(hr) + norm.ppf(fr))
        else:
            r["d_prime"] = np.nan
            r["criterion_c"] = np.nan
        r["Mean_Session_Correct_Touch_Latency_s"] = (
            pd.to_numeric(g[correct_lat], errors="coerce").mean() if correct_lat else np.nan
        )
        r["Mean_Session_Reward_Retrieval_Latency_s"] = (
            pd.to_numeric(g[reward_lat], errors="coerce").mean() if reward_lat else np.nan
        )
        rows.append(r)
    return clean_meta(pd.DataFrame(rows))

def make_iti_decile_animal_metrics(trial):
    """Decile vigilance metrics split by 2/3 s ITI."""
    if trial.empty or "Session_Progress_Decile" not in trial.columns or "Current_ITI_s" not in trial.columns:
        return pd.DataFrame()
    d = trial.copy()
    d["Current_ITI_s"] = pd.to_numeric(d["Current_ITI_s"], errors="coerce")
    d = d[d["Current_ITI_s"].isin([2, 3])].copy()
    if d.empty:
        return pd.DataFrame()
    rows = []
    for iti, g in d.groupby("Current_ITI_s", dropna=False):
        part = make_decile_animal_metrics(g)
        if not part.empty:
            part["Current_ITI_s"] = int(iti)
            rows.append(part)
    return clean_meta(pd.concat(rows, ignore_index=True)) if rows else pd.DataFrame()

def iti_whole_session(iti_animal):
    if iti_animal.empty:
        return pd.DataFrame()
    d = iti_animal[iti_animal["Session_Half"].isin(["First half", "Last half"])].copy()
    if d.empty:
        return iti_animal.copy()
    grp = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s", "Current_ITI_s"]
    agg = {
        "N_Trials": "sum",
        "Hit_Rate": "mean",
        "False_Alarm_Rate": "mean",
        "d_prime": "mean",
        "criterion_c": "mean",
        "Mean_Session_Correct_Touch_Latency_s": "mean",
        "Mean_Session_Reward_Retrieval_Latency_s": "mean",
    }
    return d.groupby(grp, as_index=False, dropna=False).agg(agg)


def within_session_decile_story_page(pdf, project, tp, sex, deciles, page_kind):
    """Ten-bin within-session vigilance story, four SD panels per metric."""
    if deciles.empty:
        return
    d = deciles[
        (deciles["Project"] == project) &
        (pd.to_numeric(deciles["Timepoint_Months"], errors="coerce") == tp) &
        (deciles["Sex"] == sex)
    ].copy()
    if d.empty:
        return

    if page_kind == "rates":
        metrics = [("Hit_Rate", "Hit rate (%)", True),
                   ("False_Alarm_Rate", "False alarm rate (%)", True)]
        page_title = "within-session vigilance: hit and false-alarm rates"
    elif page_kind == "signal":
        metrics = [("d_prime", "d prime", False),
                   ("criterion_c", "Response bias (c)", False)]
        page_title = "within-session vigilance: signal detection"
    else:
        metrics = [("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
                   ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False)]
        page_title = "within-session vigilance: latencies"

    styles = group_style_map(project)
    fig, axes = plt.subplots(2, 4, figsize=(16, 9), sharex=True)
    fig.suptitle(f"{project} - {tp} months - {sex}: {page_title}",
                 fontsize=19, fontweight="bold", y=.985)
    legend_handles = legend_labels = None

    for row_i, (col, label, percent) in enumerate(metrics):
        for di, dur in enumerate(DURS):
            ax = axes[row_i, di]
            dd = d[np.isclose(pd.to_numeric(d["Stimulus_Duration_s"], errors="coerce"), dur)].copy()
            allvals = []
            for geno, trt in GROUP_ORDER[project]:
                gd = dd[(dd["Genotype"] == geno) & (dd["Treatment"] == trt)]
                if gd.empty or col not in gd.columns:
                    continue
                # Average repeated Probe sessions within mouse before calculating group mean/SEM.
                av = gd.groupby(["Animal_ID", "Session_Progress_Decile"], as_index=False)[col].mean()
                xs, ys, es = [], [], []
                for dec in range(1, 11):
                    s = metric_values(av.loc[pd.to_numeric(av["Session_Progress_Decile"], errors="coerce").eq(dec), col], percent).dropna()
                    if s.empty:
                        continue
                    xs.append(dec); ys.append(float(s.mean())); es.append(sem(s))
                if not xs:
                    continue
                st = styles[(geno, trt)]
                ax.errorbar(xs, ys, yerr=es, marker="o", markersize=3.8, capsize=2.2,
                            color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                            label=f"{geno} | {trt} (n={av['Animal_ID'].nunique()})")
                allvals.extend((np.array(ys) + np.array(es)).tolist())
                allvals.extend((np.array(ys) - np.array(es)).tolist())
            ax.set_title(f"{dur:g} s", fontsize=10, fontweight="bold")
            ax.set_xticks([2, 4, 6, 8, 10])
            ax.set_xticklabels(["20", "40", "60", "80", "100"])
            if row_i == 1:
                ax.set_xlabel("Session progress (% image presentations)", fontsize=7.5)
            if di == 0:
                ax.set_ylabel(label, fontsize=8)
            ax.grid(alpha=.20)
            ax.tick_params(labelsize=7.5)
            add_sex_watermark(ax, sex)
            apply_smart_ylim(ax, allvals, percent)
            if legend_handles is None:
                legend_handles, legend_labels = ax.get_legend_handles_labels()

    count_df = deciles[
        (deciles["Project"] == project) &
        (deciles["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.4)
    fig.text(.5, .012,
             "Ten equal bins of image-presentation order within each session. Each mouse is averaged across its Probe sessions before group mean +/- SEM. Correction trials are excluded from standard CPT metrics.",
             ha="center", fontsize=8.1)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_within_session_decile_metric(ax, project, tp, sex, deciles, dur, col, label, percent):
    d = deciles[
        (deciles["Project"] == project) &
        (pd.to_numeric(deciles["Timepoint_Months"], errors="coerce") == tp) &
        (deciles["Sex"] == sex) &
        (np.isclose(pd.to_numeric(deciles["Stimulus_Duration_s"], errors="coerce"), dur))
    ].copy()
    if d.empty:
        ax.axis("off")
        return

    styles = group_style_map(project)
    allvals = []
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty or col not in gd.columns:
            continue
        av = gd.groupby(["Animal_ID", "Session_Progress_Decile"], as_index=False)[col].mean()
        xs, ys, es = [], [], []
        for dec in range(1, 11):
            s = metric_values(
                av.loc[pd.to_numeric(av["Session_Progress_Decile"], errors="coerce").eq(dec), col],
                percent
            ).dropna()
            if s.empty:
                continue
            xs.append(dec)
            ys.append(float(s.mean()))
            es.append(sem(s))
        if not xs:
            continue
        st = styles[(geno, trt)]
        ax.errorbar(xs, ys, yerr=es, marker="o", markersize=3.6, capsize=2.0,
                    color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"])
        allvals.extend((np.array(ys) + np.array(es)).tolist())
        allvals.extend((np.array(ys) - np.array(es)).tolist())

    ax.set_title(f"{sex}: {dur:g} s", fontsize=9.5, fontweight="bold")
    ax.set_xticks([2, 4, 6, 8, 10])
    ax.set_xticklabels(["20", "40", "60", "80", "100"])
    ax.set_xlabel("Session progress (% image presentations)", fontsize=7.5)
    ax.set_ylabel(label, fontsize=9, fontweight="bold", labelpad=8)
    ax.grid(alpha=.20)
    ax.tick_params(axis="both", labelsize=8)
    add_sex_watermark(ax, sex)
    apply_smart_ylim(ax, allvals, percent)


def within_session_decile_comparison_pages(pdf, project, tp, deciles, page_kind):
    if deciles.empty:
        return
    if page_kind == "rates":
        metrics = [("Hit_Rate", "Hit rate (%)", True),
                   ("False_Alarm_Rate", "False alarm rate (%)", True)]
        page_title = "within-session vigilance rates"
    elif page_kind == "signal":
        metrics = [("d_prime", "d prime", False),
                   ("criterion_c", "Response bias (c)", False)]
        page_title = "within-session signal detection"
    else:
        metrics = [("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
                   ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False)]
        page_title = "within-session latencies"

    dur_chunks = [DURS[i:i + 2] for i in range(0, len(DURS), 2)]
    total_pages = len(metrics) * len(dur_chunks)
    page_no = 0
    for metric_i, (col, label, percent) in enumerate(metrics, start=1):
        for dur_chunk in dur_chunks:
            page_no += 1
            fig, axes = plt.subplots(len(dur_chunk), 2, figsize=(16, 9), sharex=True, squeeze=False)
            dur_title = " & ".join(f"{d:g} s" for d in dur_chunk)
            fig.suptitle(
                f"{project} - {tp} months: {page_title} - {label} - {dur_title}",
                fontsize=18, fontweight="bold", y=.985
            )
            plotted_axes = []
            for row_i, dur in enumerate(dur_chunk):
                for col_i, sex in enumerate(SEXES):
                    ax = axes[row_i, col_i]
                    _plot_within_session_decile_metric(
                        ax, project, tp, sex, deciles, dur, col, label, percent
                    )
                    plotted_axes.append(ax)
            sync_y_limits(plotted_axes)

            count_df = deciles[
                (deciles["Project"] == project) &
                (deciles["Timepoint_Months"] == tp)
            ].copy()
            combined_group_legend(fig, project, count_df, y=.047, fontsize=8.4)
            fig.text(.5, .012,
                     "Female panels are on the left; male panels are on the right. "
                     "Rows are stimulus durations. Y-axis is matched across panels on each slide.",
                     ha="center", fontsize=8.1)
            fig.tight_layout(rect=[.02, .16, .98, .94])
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


def within_session_page(pdf, project, tp, sex, bins, dur):
    d = bins[
        (bins["Project"] == project) &
        (bins["Timepoint_Months"] == tp) &
        (bins["Sex"] == sex) &
        (np.isclose(bins["Stimulus_Duration_s"], dur))
    ].copy()
    if d.empty:
        return
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    width = .26
    half_offsets = {"First half": -width / 2, "Last half": width / 2}
    cats = ["First half", "Last half"]
    centers = np.arange(len(group_present), dtype=float)
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex} - {dur:g} s: within-session vigilance",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd.empty:
                continue
            av = gd.groupby(["Animal_ID", "Session_Half"], as_index=False)[col].mean()
            means, errors = [], []
            for ci, cat in enumerate(cats):
                s = metric_values(av.loc[av["Session_Half"] == cat, col], percent).dropna()
                means.append(float(s.mean()) if not s.empty else np.nan)
                errors.append(sem(s))
                if s.empty:
                    continue
                jitter = np.linspace(-.03, .03, len(s)) if len(s) > 1 else np.array([0.0])
                xpos = centers[gi] + half_offsets[cat]
                ax.scatter(np.full(len(s), xpos) + jitter, s, s=15,
                           color=colors[(geno, trt)], edgecolors="white",
                           linewidths=.35, zorder=4)
                allvals.extend(s.tolist())
                if np.isfinite(means[-1]):
                    allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]
            xpos = np.array([centers[gi] + half_offsets[cat] for cat in cats])
            ax.bar(xpos, means, width=width, color=colors[(geno, trt)], alpha=.58,
                   edgecolor="0.35", linewidth=.65,
                   label=f"{geno} | {trt} (n={av['Animal_ID'].nunique()})",
                   zorder=2)
            ax.errorbar(xpos, means, yerr=errors, fmt="none", ecolor="0.20",
                        elinewidth=1.05, capsize=2.8, capthick=1.05, zorder=7)
            if all(np.isfinite(means)):
                ax.plot(xpos, means, color="0.25", linewidth=.85, alpha=.65, zorder=6)
        ax.set_xticks(centers)
        ax.set_xticklabels([f"{g}\n{t}" for g, t in group_present], fontsize=7)
        ax.set_xlabel("Group (left bar = first half; right bar = last half)", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(f"{dur_label(dur)} {label}", fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)

    axes.flat[7].axis("off")
    count_df = bins[
        (bins["Project"] == project) &
        (bins["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Within-session halves are normalized by image-presentation order for this stimulus duration: first 50% of image presentations vs last 50%, not clock time. Thin grey line connects group means.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def within_session_percent_change_page(pdf, project, tp, sex, bins, dur):
    d = bins[
        (bins["Project"] == project) &
        (bins["Timepoint_Months"] == tp) &
        (bins["Sex"] == sex) &
        (np.isclose(bins["Stimulus_Duration_s"], dur))
    ].copy()
    if d.empty:
        return
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    centers = np.arange(len(group_present), dtype=float)

    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex} - {dur:g} s: % change across session halves",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd.empty:
                continue
            av = gd.groupby(["Animal_ID", "Session_Half"], as_index=False)[col].mean()
            wide = av.pivot(index="Animal_ID", columns="Session_Half", values=col)
            if not {"First half", "Last half"}.issubset(wide.columns):
                continue
            base = metric_values(wide["First half"], percent)
            follow = metric_values(wide["Last half"], percent)
            s = percent_change(follow, base).dropna()
            if s.empty:
                continue
            mean, err = float(s.mean()), sem(s)
            ax.bar([centers[gi]], [mean], yerr=[err], width=.52, capsize=3,
                   color=colors[(geno, trt)], alpha=.60, edgecolor="0.35",
                   linewidth=.65, label=f"{geno} | {trt} (n={len(s)})", zorder=2)
            jitter = np.linspace(-.055, .055, len(s)) if len(s) > 1 else np.array([0.0])
            ax.scatter(np.full(len(s), centers[gi]) + jitter, s, s=17,
                       color=colors[(geno, trt)], edgecolors="white",
                       linewidths=.35, zorder=4)
            allvals.extend(s.tolist())
            allvals.extend([mean + err, mean - err])
        ax.axhline(0, color="0.15", linewidth=1.1, alpha=.85)
        ax.set_xticks(centers)
        ax.set_xticklabels([f"{g}\n{t}" for g, t in group_present], fontsize=7)
        ax.set_ylabel("% change", fontsize=8)
        ax.set_title(f"{dur_label(dur)} {label}: last vs first", fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_change_ylim(ax, allvals)

    axes.flat[7].axis("off")
    count_df = bins[
        (bins["Project"] == project) &
        (bins["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Zero line = no change. Percent change is per mouse using normalized image-presentation halves: (last 50% - first 50%) / first 50% x 100.",
             ha="center", fontsize=8.4)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def comparison_vigilance_page(pdf, project, sex, bins, dur):
    d = bins[
        (bins["Project"] == project) &
        (bins["Sex"] == sex) &
        (np.isclose(bins["Stimulus_Duration_s"], dur))
    ].copy()
    if d.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    fig.suptitle(f"{project} - {sex} - {dur:g} s: vigilance across 6 / 9 / 12 months",
                 fontsize=20, fontweight="bold", y=.985)
    base = group_color_map(project)
    markers = {6: "o", 9: "s", 12: "^"}

    for i, (col, label, percent) in enumerate(MAIN_METRICS):
        ax = axes.flat[i]
        allvals = []
        for geno, trt in GROUP_ORDER[project]:
            gd0 = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd0.empty:
                continue
            for tp in TPS:
                gd = gd0[gd0["Timepoint_Months"] == tp]
                if gd.empty:
                    continue
                av = gd.groupby(["Animal_ID", "Session_Half"], as_index=False)[col].mean()
                xs, ys, es = [], [], []
                for xi, half in enumerate(["First half", "Last half"]):
                    s = metric_values(av.loc[av["Session_Half"] == half, col], percent).dropna()
                    if s.empty:
                        continue
                    xs.append(xi); ys.append(float(s.mean())); es.append(sem(s))
                if not xs:
                    continue
                alpha = {6: .95, 9: .72, 12: .50}.get(tp, .8)
                ax.errorbar(xs, ys, yerr=es, marker=markers.get(tp, "o"), markersize=3.5,
                            capsize=1.5, color=base[(geno, trt)], alpha=alpha,
                            linestyle="-" if trt == project_controls(project)[1] else ":",
                            linewidth=1.8,
                            label=f"{geno} | {trt} | {tp} mo (n={av['Animal_ID'].nunique()})")
                allvals.extend(np.array(ys) + np.array(es))
                allvals.extend(np.array(ys) - np.array(es))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["First half", "Last half"])
        ax.set_xlim(-.2, 1.2)
        ax.set_xlabel("Within-session image presentations", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(f"{dur_label(dur)} {label}", fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)
    count_df = bins[bins["Project"] == project].copy()
    combined_group_legend(fig, project, count_df, y=.035, fontsize=6.8)
    fig.text(.5, .008,
             "Each line compares first 50% vs last 50% of image presentations for this stimulus duration, normalizing session length/trial count. Marker shape encodes month.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=[.02, .17, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def make_next_trial_animal(nxt):
    if nxt.empty:
        return pd.DataFrame()
    d = nxt.copy()
    prev_sd_col = next((c for c in [
        "Previous_Stimulus_Duration_s",
        "Previous_Stimulus_Duration",
        "Previous_SD_s",
        "Previous_Trial_Stimulus_Duration_s",
        "Prev_Stimulus_Duration_s",
    ] if c in d.columns), None)
    if prev_sd_col:
        prev_sd = pd.to_numeric(d[prev_sd_col], errors="coerce")
        # Accept both seconds (0.2, 0.5, 1, 2) and milliseconds (200, 500, 1000, 2000).
        prev_sd_s = prev_sd.astype(float).copy()
        prev_sd_s.loc[prev_sd_s > 10] = prev_sd_s.loc[prev_sd_s > 10] / 1000.0
        d["Previous_Difficulty_Class"] = pd.Series(np.nan, index=d.index, dtype="object")
        hard = np.isclose(prev_sd_s, 0.2, atol=.01) | np.isclose(prev_sd_s, 0.5, atol=.01)
        easy = np.isclose(prev_sd_s, 1.0, atol=.01) | np.isclose(prev_sd_s, 2.0, atol=.01)
        d.loc[hard, "Previous_Difficulty_Class"] = "After hard previous trial (0.2/0.5 s)"
        d.loc[easy, "Previous_Difficulty_Class"] = "After easy previous trial (1.0/2.0 s)"
    else:
        d["Previous_Difficulty_Class"] = np.nan

    rows = []
    group_cols = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
                  "Timepoint_Months", "Previous_Outcome_Class", "Previous_Difficulty_Class"]
    from scipy.stats import norm
    for key, g in d.groupby(group_cols, dropna=False):
        r = dict(zip(group_cols, key))
        h = pd.to_numeric(g["Current_Hit"], errors="coerce").fillna(0).sum()
        m = pd.to_numeric(g["Current_Miss"], errors="coerce").fillna(0).sum()
        fa = pd.to_numeric(g["Current_False_Alarm"], errors="coerce").fillna(0).sum()
        cr = pd.to_numeric(g["Current_Correct_Rejection"], errors="coerce").fillna(0).sum()
        r["Hit_Rate"] = h / (h + m) if h + m else np.nan
        r["False_Alarm_Rate"] = fa / (fa + cr) if fa + cr else np.nan
        if h + m and fa + cr:
            hr = (h + .5) / (h + m + 1)
            fr = (fa + .5) / (fa + cr + 1)
            r["d_prime"] = norm.ppf(hr) - norm.ppf(fr)
            r["criterion_c"] = -.5 * (norm.ppf(hr) + norm.ppf(fr))
        else:
            r["d_prime"] = np.nan
            r["criterion_c"] = np.nan
        latency_map = {
            "Mean_Session_Correct_Touch_Latency_s": [
                "Correct_Touch_Latency_AnalysisClean_s",
                "Correct_Touch_Latency_s",
                "Correct_Touch_Latency_IQRclean_s",
                "Mean_Session_Correct_Touch_Latency_s",
            ],
            "Mean_Session_Incorrect_Touch_Latency_s": [
                "Incorrect_Touch_Latency_AnalysisClean_s",
                "Incorrect_Touch_Latency_s",
                "Incorrect_Touch_Latency_IQRclean_s",
                "Mean_Session_Incorrect_Touch_Latency_s",
            ],
            "Mean_Session_Reward_Retrieval_Latency_s": [
                "Reward_Retrieval_Latency_AnalysisClean_s",
                "Reward_Retrieval_Latency_s",
                "Reward_Retrieval_Latency_IQRclean_s",
                "Mean_Session_Reward_Retrieval_Latency_s",
            ],
        }
        for out_col, candidates in latency_map.items():
            src = first_present(g, candidates)
            r[out_col] = pd.to_numeric(g[src], errors="coerce").mean() if src else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def _canonical_outcome_detail(series):
    """Map trial outcome text to Hit / Correct Rejection / Miss / False Alarm."""
    s = series.astype(str).str.strip().str.lower()
    out = pd.Series(np.nan, index=series.index, dtype="object")
    out.loc[s.str.fullmatch(r"hit", na=False)] = "Hit"
    out.loc[s.str.contains(r"correct\s*rejection|correct_rejection|\bcr\b", regex=True, na=False)] = "Correct Rejection"
    out.loc[s.str.fullmatch(r"miss", na=False)] = "Miss"
    out.loc[s.str.contains(r"false\s*alarm|false_alarm|\bfa\b", regex=True, na=False)] = "False Alarm"
    return out


def _prepare_core_trial_sequence(trial):
    """Return standard CPT trials with previous outcome rebuilt after excluding correction trials.

    Correction trials are task-imposed after errors (especially false alarms). Including
    them as the "next trial" can create artificial 0/100% stay values and make the
    After-FA category appear missing. For feedback/history analyses, the next trial is
    the next standard (non-correction) CPT image presentation.
    """
    if trial.empty:
        return pd.DataFrame()

    d = trial.copy()
    outcome_col = first_present(d, ["Outcome", "Current_Outcome", "Trial_Outcome"])
    if outcome_col is None:
        return pd.DataFrame()

    d["Current_Outcome_Detail"] = _canonical_outcome_detail(d[outcome_col])

    corr = pd.Series(False, index=d.index)
    if "Current_Trial_Is_Correction" in d.columns:
        corr |= pd.to_numeric(d["Current_Trial_Is_Correction"], errors="coerce").fillna(0).gt(0)
    corr |= d[outcome_col].astype(str).str.strip().str.lower().str.startswith("correction trial")
    for c in ["Correction_Trial_Correct_Rejection", "Correction_Trial_Mistake"]:
        if c in d.columns:
            corr |= pd.to_numeric(d[c], errors="coerce").fillna(0).gt(0)

    d = d[(~corr) & d["Current_Outcome_Detail"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    session_keys = [c for c in [
        "Project", "Animal_ID", "Timepoint_Months", "Probe_Session_Number",
        "Source_Database", "Database_Fingerprint", "SID", "Session_DateTime"
    ] if c in d.columns]
    if not session_keys:
        return pd.DataFrame()

    sort_cols = session_keys.copy()
    trial_index_col = first_present(d, ["Trial_Index", "Trial_Counter", "Image_Presentation_Index"])
    if trial_index_col:
        d[trial_index_col] = pd.to_numeric(d[trial_index_col], errors="coerce")
        sort_cols.append(trial_index_col)

    d = d.sort_values(sort_cols, kind="mergesort").copy()
    d["Previous_Outcome_Detail"] = (
        d.groupby(session_keys, dropna=False)["Current_Outcome_Detail"].shift(1)
    )
    d = d[d["Previous_Outcome_Detail"].notna()].copy()
    return d


def make_feedback_next_trial_animal(trial):
    """Detailed previous-outcome -> next-standard-trial metrics."""
    d = _prepare_core_trial_sequence(trial)
    if d.empty:
        return pd.DataFrame()

    d["Current_Hit"] = d["Current_Outcome_Detail"].eq("Hit").astype(int)
    d["Current_Miss"] = d["Current_Outcome_Detail"].eq("Miss").astype(int)
    d["Current_False_Alarm"] = d["Current_Outcome_Detail"].eq("False Alarm").astype(int)
    d["Current_Correct_Rejection"] = d["Current_Outcome_Detail"].eq("Correct Rejection").astype(int)

    group_cols = [c for c in [
        "Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
        "Timepoint_Months", "Previous_Outcome_Detail"
    ] if c in d.columns]
    required_meta = {"Project", "Animal_ID", "Sex", "Genotype", "Treatment", "Timepoint_Months"}
    if not required_meta.issubset(group_cols):
        return pd.DataFrame()

    from scipy.stats import norm
    rows = []
    for key, g in d.groupby(group_cols, dropna=False):
        r = dict(zip(group_cols, key if isinstance(key, tuple) else (key,)))
        h = g["Current_Hit"].sum()
        m = g["Current_Miss"].sum()
        fa = g["Current_False_Alarm"].sum()
        cr = g["Current_Correct_Rejection"].sum()

        r["Hit_Rate"] = h / (h + m) if h + m else np.nan
        r["False_Alarm_Rate"] = fa / (fa + cr) if fa + cr else np.nan

        if h + m and fa + cr:
            hr = (h + .5) / (h + m + 1)
            fr = (fa + .5) / (fa + cr + 1)
            r["d_prime"] = norm.ppf(hr) - norm.ppf(fr)
            r["criterion_c"] = -.5 * (norm.ppf(hr) + norm.ppf(fr))
        else:
            r["d_prime"] = np.nan
            r["criterion_c"] = np.nan

        latency_specs = {
            "Mean_Session_Correct_Touch_Latency_s": [
                "Correct_Touch_Latency_AnalysisClean_s",
                "Correct_Touch_Latency_IQRclean_s",
                "Correct_Touch_Latency_s",
            ],
            "Mean_Session_Incorrect_Touch_Latency_s": [
                "Incorrect_Touch_Latency_AnalysisClean_s",
                "Incorrect_Touch_Latency_IQRclean_s",
                "Incorrect_Touch_Latency_s",
            ],
            "Mean_Session_Reward_Retrieval_Latency_s": [
                "Reward_Retrieval_Latency_AnalysisClean_s",
                "Reward_Retrieval_Latency_IQRclean_s",
                "Reward_Retrieval_Latency_s",
            ],
        }
        for out_col, opts in latency_specs.items():
            src_col = first_present(g, opts)
            r[out_col] = pd.to_numeric(g[src_col], errors="coerce").mean() if src_col else np.nan

        r["Next_Target_Trials"] = float(h + m)
        r["Next_Nontarget_Trials"] = float(fa + cr)
        rows.append(r)

    return clean_meta(pd.DataFrame(rows))


def make_response_transition_animal(trial):
    """Response-stay/shift on the next standard CPT trial after a specific outcome."""
    d = _prepare_core_trial_sequence(trial)
    if d.empty:
        return pd.DataFrame()

    d["Next_Stimulus_Class"] = pd.Series(pd.NA, index=d.index, dtype="object")
    d.loc[d["Current_Outcome_Detail"].isin(["Hit", "Miss"]), "Next_Stimulus_Class"] = "Target"
    d.loc[d["Current_Outcome_Detail"].isin(["False Alarm", "Correct Rejection"]), "Next_Stimulus_Class"] = "Non-target"

    d["Next_Response"] = pd.Series(pd.NA, index=d.index, dtype="object")
    d.loc[d["Current_Outcome_Detail"].isin(["Hit", "False Alarm"]), "Next_Response"] = "Touch"
    d.loc[d["Current_Outcome_Detail"].isin(["Miss", "Correct Rejection"]), "Next_Response"] = "Withhold"

    d["Previous_Response"] = pd.Series(pd.NA, index=d.index, dtype="object")
    d.loc[d["Previous_Outcome_Detail"].isin(["Hit", "False Alarm"]), "Previous_Response"] = "Touch"
    d.loc[d["Previous_Outcome_Detail"].isin(["Miss", "Correct Rejection"]), "Previous_Response"] = "Withhold"

    d = d[d["Next_Stimulus_Class"].notna() & d["Previous_Response"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    d["Response_Stay"] = (d["Previous_Response"] == d["Next_Response"]).astype(float)
    d["Next_Touch"] = (d["Next_Response"] == "Touch").astype(float)
    d["Next_Correct"] = d["Current_Outcome_Detail"].isin(["Hit", "Correct Rejection"]).astype(float)

    group_cols = [c for c in [
        "Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
        "Timepoint_Months", "Previous_Outcome_Detail", "Next_Stimulus_Class"
    ] if c in d.columns]
    required_meta = {"Project", "Animal_ID", "Sex", "Genotype", "Treatment", "Timepoint_Months"}
    if not required_meta.issubset(group_cols):
        return pd.DataFrame()

    out_df = d.groupby(group_cols, dropna=False).agg(
        Response_Stay_Rate=("Response_Stay", "mean"),
        Next_Touch_Rate=("Next_Touch", "mean"),
        Next_Correct_Rate=("Next_Correct", "mean"),
        N_Transitions=("Response_Stay", "size"),
    ).reset_index()

    return clean_meta(out_df)


def make_correction_trial_animal(trial):
    """Derive mouse-level correction-trial metrics directly from PROBE2B_TRIAL_MASTER.

    Correction trials are identified from the explicit extractor flags
    Correction_Trial_Correct_Rejection / Correction_Trial_Mistake, with Outcome
    text as a fallback. Standard CPT HR/FAR/d-prime/c are NOT recalculated here.
    """
    if trial.empty:
        return pd.DataFrame()

    d = trial.copy()
    cr_col = first_present(d, [
        "Correction_Trial_Correct_Rejection",
        "CorrectionTrialCorrectRejection",
        "Correction_Trial_CR",
        "CorrectionTrialCR",
    ])
    mistake_col = first_present(d, [
        "Correction_Trial_Mistake",
        "CorrectionTrialMistake",
        "Correction_Trial_Error",
        "CorrectionTrialError",
    ])
    outcome_col = first_present(d, ["Outcome", "Trial_Outcome", "Current_Outcome"])

    if cr_col is None and mistake_col is None and outcome_col is None:
        return pd.DataFrame()

    for c in ["Stimulus_Duration_s", "Timepoint_Months", "Probe_Session_Number",
              "Trial_Index", "Trial_Counter"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    cr = pd.to_numeric(d[cr_col], errors="coerce").fillna(0) if cr_col else pd.Series(0, index=d.index)
    mistake = pd.to_numeric(d[mistake_col], errors="coerce").fillna(0) if mistake_col else pd.Series(0, index=d.index)

    if outcome_col:
        outcome = d[outcome_col].fillna("").astype(str).str.strip().str.lower()
        outcome_is_corr = outcome.str.startswith("correction trial")
        outcome_is_cr = outcome.str.contains("correction trial correct rejection", regex=False)
        outcome_is_mistake = outcome.str.contains("correction trial mistake", regex=False)
    else:
        outcome_is_corr = pd.Series(False, index=d.index)
        outcome_is_cr = pd.Series(False, index=d.index)
        outcome_is_mistake = pd.Series(False, index=d.index)

    d["_CT_CR"] = ((cr > 0) | outcome_is_cr).astype(int)
    d["_CT_Mistake"] = ((mistake > 0) | outcome_is_mistake).astype(int)
    d["_Is_Correction"] = ((d["_CT_CR"] > 0) | (d["_CT_Mistake"] > 0) | outcome_is_corr).astype(int)

    required_meta = ["Project", "Animal_ID", "Sex", "Genotype", "Treatment",
                     "Timepoint_Months", "Stimulus_Duration_s"]
    if any(c not in d.columns for c in required_meta):
        return pd.DataFrame()

    if "Cohort" not in d.columns:
        d["Cohort"] = ""
    if "Probe_Session_Number" not in d.columns:
        d["Probe_Session_Number"] = np.nan

    # Build consecutive correction-trial chains within a session.
    sort_cols = [c for c in ["Project", "Animal_ID", "Timepoint_Months",
                             "Probe_Session_Number", "SID", "Trial_Index", "Trial_Counter"] if c in d.columns]
    d = d.sort_values(sort_cols, kind="mergesort").copy()

    session_keys = [c for c in ["Project", "Animal_ID", "Timepoint_Months",
                                "Probe_Session_Number", "SID"] if c in d.columns]
    chain_records = []
    if session_keys:
        for _, g in d.groupby(session_keys, dropna=False, sort=False):
            g = g.sort_values([c for c in ["Trial_Index", "Trial_Counter"] if c in g.columns],
                              kind="mergesort")
            in_chain = False
            chain_rows = []
            for idx, row in g.iterrows():
                is_corr = int(row["_Is_Correction"]) == 1
                if is_corr:
                    if not in_chain:
                        chain_rows = []
                        in_chain = True
                    chain_rows.append(row)
                elif in_chain:
                    if chain_rows:
                        first = chain_rows[0]
                        chain_records.append({
                            "Project": first["Project"],
                            "Animal_ID": first["Animal_ID"],
                            "Cohort": first.get("Cohort", ""),
                            "Sex": first["Sex"],
                            "Genotype": first["Genotype"],
                            "Treatment": first["Treatment"],
                            "Timepoint_Months": first["Timepoint_Months"],
                            "Stimulus_Duration_s": first["Stimulus_Duration_s"],
                            "Chain_Attempts": len(chain_rows),
                            "First_Attempt_Success": int(first["_CT_CR"] > 0),
                        })
                    chain_rows = []
                    in_chain = False
            if in_chain and chain_rows:
                first = chain_rows[0]
                chain_records.append({
                    "Project": first["Project"],
                    "Animal_ID": first["Animal_ID"],
                    "Cohort": first.get("Cohort", ""),
                    "Sex": first["Sex"],
                    "Genotype": first["Genotype"],
                    "Treatment": first["Treatment"],
                    "Timepoint_Months": first["Timepoint_Months"],
                    "Stimulus_Duration_s": first["Stimulus_Duration_s"],
                    "Chain_Attempts": len(chain_rows),
                    "First_Attempt_Success": int(first["_CT_CR"] > 0),
                })

    base_keys = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
                 "Timepoint_Months", "Stimulus_Duration_s"]

    rows = []
    for key, g in d.groupby(base_keys, dropna=False):
        r = dict(zip(base_keys, key))
        n_total = int(len(g))
        n_corr = int(g["_Is_Correction"].sum())
        n_cr = int(g["_CT_CR"].sum())
        n_mistake = int(g["_CT_Mistake"].sum())
        denom_corr = n_cr + n_mistake

        r["Correction_Trial_Count"] = n_corr
        r["Total_Presentation_Count"] = n_total
        r["Correction_Trial_Burden"] = n_corr / n_total if n_total else np.nan
        r["Correction_Success_Rate"] = n_cr / denom_corr if denom_corr else np.nan
        r["Correction_Mistake_Rate"] = n_mistake / denom_corr if denom_corr else np.nan
        rows.append(r)

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    chains = pd.DataFrame(chain_records)
    if not chains.empty:
        chain_av = chains.groupby(base_keys, dropna=False).agg(
            Mean_Correction_Attempts_Per_Chain=("Chain_Attempts", "mean"),
            First_Attempt_Correction_Success=("First_Attempt_Success", "mean"),
            Correction_Chain_Count=("Chain_Attempts", "size"),
        ).reset_index()
        out = out.merge(chain_av, on=base_keys, how="left")
    else:
        out["Mean_Correction_Attempts_Per_Chain"] = np.nan
        out["First_Attempt_Correction_Success"] = np.nan
        out["Correction_Chain_Count"] = 0

    return clean_meta(out)


def correction_trial_page(pdf, project, tp, sex, correction_animal):
    """Four-panel correction-trial summary by stimulus duration."""
    if correction_animal.empty:
        return

    d = correction_animal[
        (correction_animal["Project"] == project) &
        (correction_animal["Timepoint_Months"] == tp) &
        (correction_animal["Sex"] == sex)
    ].copy()
    if d.empty or pd.to_numeric(d.get("Correction_Trial_Count"), errors="coerce").fillna(0).sum() <= 0:
        return

    metrics = [
        ("Correction_Trial_Burden", "Correction trials (% presentations)", True),
        ("Correction_Success_Rate", "Correction-trial success (%)", True),
        ("First_Attempt_Correction_Success", "Solved on first correction (%)", True),
        ("Mean_Correction_Attempts_Per_Chain", "Correction attempts per chain", False),
    ]
    metric_explanations = {
        "Correction_Trial_Burden": "Useful because it shows how often mice enter the correction procedure; higher values suggest more initial errors.",
        "Correction_Success_Rate": "Useful because it shows whether mice usually recover once correction trials occur; lower values suggest difficulty resolving errors.",
        "First_Attempt_Correction_Success": "Useful because it highlights immediate recovery after an error; lower values suggest repeated errors or perseveration.",
        "Mean_Correction_Attempts_Per_Chain": "Useful because it captures how many repeated correction attempts are needed; higher values suggest more persistent responding.",
    }

    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    if not group_present:
        return

    offsets = np.linspace(-.22, .22, max(1, len(group_present)))
    width = .13

    fig, axes = plt.subplots(1, 4, figsize=(16, 5.8))
    fig.suptitle(f"{project} - {tp} months - {sex}: correction-trial behavior",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(metrics):
        ax = axes.flat[i]
        allvals = []
        if col not in d.columns:
            ax.axis("off")
            continue

        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            xpos = np.arange(len(DURS), dtype=float) + offsets[gi]
            means, errors = [], []

            for di, dur in enumerate(DURS):
                cell = gd[np.isclose(pd.to_numeric(gd["Stimulus_Duration_s"], errors="coerce"),
                                     dur, atol=.01)]
                s = metric_values(cell[col], percent).dropna()
                means.append(float(s.mean()) if not s.empty else np.nan)
                errors.append(sem(s))

                if not s.empty:
                    jitter = np.linspace(-.03, .03, len(s)) if len(s) > 1 else np.array([0.0])
                    ax.scatter(np.full(len(s), xpos[di]) + jitter, s, s=15,
                               color=colors[(geno, trt)], edgecolors="white",
                               linewidths=.35, zorder=4)
                    allvals.extend(s.tolist())
                if np.isfinite(means[-1]):
                    allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]

            ax.bar(xpos, means, width=width,
                   color=colors[(geno, trt)], alpha=.58,
                   edgecolor="0.35", linewidth=.65,
                   label=f"{geno} | {trt} (n={gd['Animal_ID'].nunique()})",
                   zorder=2)
            ax.errorbar(xpos, means, yerr=errors, fmt="none",
                        ecolor="0.20", elinewidth=1.05, capsize=2.8, capthick=1.05,
                        zorder=7)

        ax.set_xticks(range(len(DURS)))
        ax.set_xticklabels(["2.0", "1.0", "0.5", "0.2"], fontsize=8)
        ax.set_xlabel("Stimulus duration (s)", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)

        # Correction-success measures sit very close to the 100% ceiling.
        # Use a zoomed ceiling view so small differences are visible.
        if col in {"Correction_Success_Rate", "First_Attempt_Correction_Success"}:
            ax.set_ylim(90.0, 105.0)
            ax.text(.02, .03, "Zoomed y-axis: 90-105%",
                    transform=ax.transAxes, ha="left", va="bottom",
                    fontsize=6.8, color="0.35")
        else:
            apply_smart_ylim(ax, allvals, percent)

    count_df = correction_animal[
        (correction_animal["Project"] == project) &
        (correction_animal["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.055, fontsize=8.4)
    fig.text(.5, .015,
             "Correction trials are identified from the explicit Trial Master correction fields. "
             "These measures are reported separately and are not added to the standard CPT HR/FAR/d-prime calculations. "
             "Dots = mouse-level values; bars = mean +/- SEM.",
             ha="center", fontsize=8.1)
    fig.tight_layout(rect=[.02, .18, .98, .90])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def trial_carryover_page(pdf, project, tp, sex, next_animal):
    if next_animal.empty or "Previous_Difficulty_Class" not in next_animal.columns:
        return
    d = next_animal[
        (next_animal["Project"] == project) &
        (next_animal["Timepoint_Months"] == tp) &
        (next_animal["Sex"] == sex)
    ].copy()
    d = d[d["Previous_Difficulty_Class"].notna()]
    if d.empty:
        return

    cats = ["After easy previous trial (1.0/2.0 s)", "After hard previous trial (0.2/0.5 s)"]
    if not any(c in set(d["Previous_Difficulty_Class"].astype(str)) for c in cats):
        return

    metrics = [
        ("Hit_Rate", "Next-trial hit rate (%)", True),
        ("False_Alarm_Rate", "Next-trial false alarm rate (%)", True),
        ("d_prime", "Next-trial d prime", False),
        ("criterion_c", "Next-trial response bias (c)", False),
        ("Mean_Session_Correct_Touch_Latency_s", "Next correct latency (s)", False),
        ("Mean_Session_Incorrect_Touch_Latency_s", "Next incorrect latency (s)", False),
        ("Mean_Session_Reward_Retrieval_Latency_s", "Next reward latency (s)", False),
    ]
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    offsets = np.linspace(-.22, .22, max(1, len(group_present)))
    width = .13

    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: next-trial behavior after easy vs hard previous trial",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(metrics):
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            cat_pos = tight_category_positions(len(cats))
            xpos = cat_pos + offsets[gi]
            means, errors = [], []
            for ci, cat in enumerate(cats):
                cell = gd[gd["Previous_Difficulty_Class"].astype(str) == cat]
                # Average over previous-outcome classes within mouse for this difficulty class.
                av = cell.groupby("Animal_ID", as_index=False)[col].mean()
                s = metric_values(av[col], percent).dropna()
                means.append(float(s.mean()) if not s.empty else np.nan)
                errors.append(sem(s))
                if not s.empty:
                    jitter = np.linspace(-.03, .03, len(s)) if len(s) > 1 else np.array([0.0])
                    ax.scatter(np.full(len(s), xpos[ci]) + jitter, s, s=15,
                               color=colors[(geno, trt)], edgecolors="white",
                               linewidths=.35, zorder=4)
                    allvals.extend(s.tolist())
                if np.isfinite(means[-1]):
                    allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]
            ax.bar(xpos, means, width=width,
                   color=colors[(geno, trt)], alpha=.58,
                   edgecolor="0.35", linewidth=.65,
                   label=f"{geno} | {trt} (n={gd['Animal_ID'].nunique()})",
                   zorder=2)
            ax.errorbar(xpos, means, yerr=errors, fmt="none",
                        ecolor="0.20", elinewidth=1.05, capsize=2.8, capthick=1.05,
                        zorder=7)

        cat_pos = tight_category_positions(len(cats))
        ax.set_xticks(cat_pos)
        ax.set_xticklabels(["Easy prev\n1.0/2.0 s" if "easy" in c else "Hard prev\n0.2/0.5 s" for c in cats],
                           fontsize=8)
        apply_tight_category_axis(ax, cat_pos)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)

    axes.flat[7].axis("off")
    count_df = next_animal[
        (next_animal["Project"] == project) &
        (next_animal["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Stimulus durations are NOT averaged here: bars split next-trial behavior by previous-trial difficulty (easy 1.0/2.0 s vs hard 0.2/0.5 s). Dots are mouse-level means.",
             ha="center", fontsize=8.2)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_trial_carryover_metric(ax, project, tp, sex, next_animal, col, label, percent):
    d = next_animal[
        (next_animal["Project"] == project) &
        (next_animal["Timepoint_Months"] == tp) &
        (next_animal["Sex"] == sex)
    ].copy()
    if d.empty or "Previous_Difficulty_Class" not in d.columns:
        ax.axis("off")
        return
    d = d[d["Previous_Difficulty_Class"].notna()]
    cats = ["After easy previous trial (1.0/2.0 s)", "After hard previous trial (0.2/0.5 s)"]
    if d.empty or not any(c in set(d["Previous_Difficulty_Class"].astype(str)) for c in cats):
        ax.axis("off")
        return

    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    offsets = np.linspace(-.22, .22, max(1, len(group_present)))
    width = .13
    allvals = []
    for gi, (geno, trt) in enumerate(group_present):
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        cat_pos = tight_category_positions(len(cats))
        xpos = cat_pos + offsets[gi]
        means, errors = [], []
        for ci, cat in enumerate(cats):
            cell = gd[gd["Previous_Difficulty_Class"].astype(str) == cat]
            av = cell.groupby("Animal_ID", as_index=False)[col].mean()
            s = metric_values(av[col], percent).dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            if not s.empty:
                jitter = np.linspace(-.03, .03, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), xpos[ci]) + jitter, s, s=12,
                           color=colors[(geno, trt)], edgecolors="white",
                           linewidths=.3, zorder=4)
                allvals.extend(s.tolist())
            if np.isfinite(means[-1]):
                allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]
        ax.bar(xpos, means, width=width, color=colors[(geno, trt)], alpha=.58,
               edgecolor="0.35", linewidth=.6, zorder=2)
        ax.errorbar(xpos, means, yerr=errors, fmt="none",
                    ecolor="0.20", elinewidth=1.0, capsize=2.6, capthick=1.0, zorder=7)

    cat_pos = tight_category_positions(len(cats))
    ax.set_xticks(cat_pos)
    ax.set_xticklabels(["Easy prev\n1.0/2.0 s", "Hard prev\n0.2/0.5 s"], fontsize=7.5)
    apply_tight_category_axis(ax, cat_pos)
    ax.set_ylabel(label, fontsize=9, fontweight="bold", labelpad=8)
    ax.set_title(f"{sex}: {label}", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(axis="y", alpha=.20)
    ax.tick_params(axis="both", labelsize=8)
    apply_smart_ylim(ax, allvals, percent)


def trial_carryover_combined_pages(pdf, project, tp, next_animal):
    metrics = [
        ("Hit_Rate", "Next-trial hit rate (%)", True),
        ("False_Alarm_Rate", "Next-trial false alarm rate (%)", True),
        ("d_prime", "Next-trial d prime", False),
        ("criterion_c", "Next-trial response bias (c)", False),
        ("Mean_Session_Correct_Touch_Latency_s", "Next correct latency (s)", False),
        ("Mean_Session_Incorrect_Touch_Latency_s", "Next incorrect latency (s)", False),
        ("Mean_Session_Reward_Retrieval_Latency_s", "Next reward latency (s)", False),
    ]
    if next_animal.empty or "Previous_Difficulty_Class" not in next_animal.columns:
        return
    chunks = [metrics[i:i + 2] for i in range(0, len(metrics), 2)]
    for page_i, chunk in enumerate(chunks, start=1):
        fig, axes = plt.subplots(len(chunk), 2, figsize=(16, 9), squeeze=False)
        fig.suptitle(
            f"{project} - {tp} months: next-trial behavior after easy vs hard previous trial "
            f"({page_i}/{len(chunks)})",
            fontsize=18, fontweight="bold", y=.985
        )
        for row_i, (col, label, percent) in enumerate(chunk):
            row_axes = []
            for col_i, sex in enumerate(SEXES):
                ax = axes[row_i, col_i]
                _plot_trial_carryover_metric(
                    ax, project, tp, sex, next_animal, col, label, percent
                )
                row_axes.append(ax)
            sync_y_limits(row_axes)
        count_df = next_animal[
            (next_animal["Project"] == project) &
            (next_animal["Timepoint_Months"] == tp)
        ].copy()
        combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
        fig.text(.5, .012,
                 "Female panels are on the left; male panels are on the right. "
                 "Bars split next-trial behavior by previous-trial difficulty. Dots are mouse-level means.",
                 ha="center", fontsize=8.2)
        fig.tight_layout(rect=[.02, .16, .98, .94])
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def next_trial_page(pdf, project, tp, sex, next_animal):
    d = next_animal[
        (next_animal["Project"] == project) &
        (next_animal["Timepoint_Months"] == tp) &
        (next_animal["Sex"] == sex)
    ].copy()
    if d.empty:
        return

    preferred = ["After correct trial", "After error/miss"]
    cats = [c for c in preferred if c in set(d["Previous_Outcome_Class"].astype(str))]
    if not cats:
        cats = sorted(d["Previous_Outcome_Class"].dropna().astype(str).unique())[:5]

    metrics = [
        ("Hit_Rate", "Next-trial hit rate (%)", True),
        ("False_Alarm_Rate", "Next-trial false alarm rate (%)", True),
        ("Mean_Session_Correct_Touch_Latency_s", "Next correct latency (s)", False),
        ("Mean_Session_Incorrect_Touch_Latency_s", "Next incorrect latency (s)", False),
        ("Mean_Session_Reward_Retrieval_Latency_s", "Next reward latency (s)", False),
    ]
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    offsets = np.linspace(-.22, .22, max(1, len(group_present)))
    width = .13

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: next-trial behavior",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(metrics):
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            cat_pos = tight_category_positions(len(cats))
            xpos = cat_pos + offsets[gi]
            means, errors = [], []
            for ci, cat in enumerate(cats):
                cell = gd[gd["Previous_Outcome_Class"].astype(str) == cat]
                s = metric_values(cell[col], percent).dropna()
                means.append(float(s.mean()) if not s.empty else np.nan)
                errors.append(sem(s))
                if not s.empty:
                    # one dot per mouse in this prior-outcome condition
                    vals = cell[["Animal_ID", col]].dropna().copy()
                    vals["PlotValue"] = metric_values(vals[col], percent)
                    jitter = np.linspace(-.03, .03, len(vals)) if len(vals) > 1 else np.array([0.0])
                    ax.scatter(
                        np.full(len(vals), xpos[ci]) + jitter,
                        vals["PlotValue"],
                        s=15, color=colors[(geno, trt)],
                        edgecolors="white", linewidths=.35, zorder=4
                    )
                    allvals.extend(vals["PlotValue"].tolist())
                if np.isfinite(means[-1]):
                    allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]

            ax.bar(
                xpos, means, width=width,
                color=colors[(geno, trt)], alpha=.58,
                edgecolor="0.35", linewidth=.65,
                label=f"{geno} | {trt} (n={gd['Animal_ID'].nunique()})",
                zorder=2
            )
            ax.errorbar(
                xpos, means, yerr=errors, fmt="none",
                ecolor="0.20", elinewidth=1.05, capsize=2.8, capthick=1.05,
                zorder=7
            )

        cat_pos = tight_category_positions(len(cats))
        ax.set_xticks(cat_pos)
        ax.set_xticklabels(cats, rotation=10, ha="center", fontsize=8)
        apply_tight_category_axis(ax, cat_pos)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(axis="y", alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)

    axes.flat[5].axis("off")
    count_df = next_animal[
        (next_animal["Project"] == project) &
        (next_animal["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.7)
    fig.text(.5, .012,
             "Stimulus durations are averaged/collapsed on this previous-outcome slide. Bars = mean +/- SEM; each dot = one mouse.",
             ha="center", fontsize=8.2)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_next_trial_outcome_metric(ax, project, tp, sex, next_animal, col, label, percent):
    d = next_animal[
        (next_animal["Project"] == project) &
        (next_animal["Timepoint_Months"] == tp) &
        (next_animal["Sex"] == sex)
    ].copy()
    if d.empty or "Previous_Outcome_Class" not in d.columns:
        ax.axis("off")
        return

    preferred = ["After correct trial", "After error/miss"]
    cats = [c for c in preferred if c in set(d["Previous_Outcome_Class"].astype(str))]
    if not cats:
        cats = sorted(d["Previous_Outcome_Class"].dropna().astype(str).unique())[:5]
    if not cats:
        ax.axis("off")
        return

    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    offsets = np.linspace(-.22, .22, max(1, len(group_present)))
    width = .13
    allvals = []
    for gi, (geno, trt) in enumerate(group_present):
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        cat_pos = tight_category_positions(len(cats))
        xpos = cat_pos + offsets[gi]
        means, errors = [], []
        for ci, cat in enumerate(cats):
            cell = gd[gd["Previous_Outcome_Class"].astype(str) == cat]
            vals = cell[["Animal_ID", col]].dropna().copy()
            if vals.empty:
                s = pd.Series(dtype=float)
            else:
                vals = vals.groupby("Animal_ID", as_index=False)[col].mean()
                vals["PlotValue"] = metric_values(vals[col], percent)
                s = vals["PlotValue"].dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            if not s.empty:
                jitter = np.linspace(-.03, .03, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), xpos[ci]) + jitter, s, s=12,
                           color=colors[(geno, trt)], edgecolors="white",
                           linewidths=.3, zorder=4)
                allvals.extend(s.tolist())
            if np.isfinite(means[-1]):
                allvals += [means[-1] + errors[-1], means[-1] - errors[-1]]
        ax.bar(xpos, means, width=width, color=colors[(geno, trt)], alpha=.58,
               edgecolor="0.35", linewidth=.6, zorder=2)
        ax.errorbar(xpos, means, yerr=errors, fmt="none",
                    ecolor="0.20", elinewidth=1.0, capsize=2.6, capthick=1.0, zorder=7)

    cat_pos = tight_category_positions(len(cats))
    ax.set_xticks(cat_pos)
    ax.set_xticklabels(cats, rotation=5, ha="center", fontsize=7.5)
    apply_tight_category_axis(ax, cat_pos)
    ax.set_ylabel(label, fontsize=9, fontweight="bold", labelpad=8)
    ax.set_title(f"{sex}: {label}", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(axis="y", alpha=.20)
    ax.tick_params(axis="both", labelsize=8)
    apply_smart_ylim(ax, allvals, percent)


def next_trial_outcome_combined_pages(pdf, project, tp, next_animal):
    metrics = [
        ("Hit_Rate", "Next-trial hit rate (%)", True),
        ("False_Alarm_Rate", "Next-trial false alarm rate (%)", True),
        ("Mean_Session_Correct_Touch_Latency_s", "Next correct latency (s)", False),
        ("Mean_Session_Incorrect_Touch_Latency_s", "Next incorrect latency (s)", False),
        ("Mean_Session_Reward_Retrieval_Latency_s", "Next reward latency (s)", False),
    ]
    if next_animal.empty or "Previous_Outcome_Class" not in next_animal.columns:
        return
    chunks = [metrics[i:i + 2] for i in range(0, len(metrics), 2)]
    for page_i, chunk in enumerate(chunks, start=1):
        fig, axes = plt.subplots(len(chunk), 2, figsize=(16, 9), squeeze=False)
        fig.suptitle(
            f"{project} - {tp} months: next-trial behavior after previous outcome "
            f"({page_i}/{len(chunks)})",
            fontsize=18, fontweight="bold", y=.985
        )
        for row_i, (col, label, percent) in enumerate(chunk):
            row_axes = []
            for col_i, sex in enumerate(SEXES):
                ax = axes[row_i, col_i]
                _plot_next_trial_outcome_metric(
                    ax, project, tp, sex, next_animal, col, label, percent
                )
                row_axes.append(ax)
            sync_y_limits(row_axes)
        count_df = next_animal[
            (next_animal["Project"] == project) &
            (next_animal["Timepoint_Months"] == tp)
        ].copy()
        combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
        fig.text(.5, .012,
                 "Female panels are on the left; male panels are on the right. "
                 "Stimulus durations are collapsed on previous-outcome slides. Dots are mouse-level means.",
                 ha="center", fontsize=8.2)
        fig.tight_layout(rect=[.02, .16, .98, .94])
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def next_trial_explainer_page(pdf, project, tp):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    fig.text(.5, .91, f"{project} - {tp} months: how to read next-trial behavior",
             ha="center", va="center", fontsize=22, fontweight="bold")
    fig.text(.5, .855,
             "Each value describes what the animal did on the trial immediately after a specific previous-trial event.",
             ha="center", va="center", fontsize=11.5, color="0.22")

    rows = [
        ("Previous difficulty effect",
         "Compares next-trial behavior after an easy previous trial (1.0/2.0 s) versus a hard previous trial (0.2/0.5 s).",
         "Useful for asking whether a hard trial carries over into the next response."),
        ("Previous outcome effect",
         "Compares next-trial behavior after a previous hit/correct response versus previous miss or mistake/error.",
         "Useful for asking whether success or failure changes the next response strategy."),
        ("Next-trial hit rate",
         "Among next trials where a signal appeared, percent correctly touched.",
         "Higher means better detection on the next signal trial."),
        ("Next-trial false alarm rate",
         "Among next trials where no signal appeared, percent incorrectly touched.",
         "Higher means more impulsive responding or weaker inhibitory control."),
        ("Next-trial latencies",
         "Correct, incorrect, and reward latencies measured on the next trial.",
         "Interpret with accuracy: faster is not always better if false alarms also rise."),
    ]

    col_x = [.06, .285, .665]
    widths = [.20, .35, .275]
    wrap_chars = [24, 58, 42]
    headers = ["Metric / Split", "What it means", "How to interpret"]
    y_top = .765
    row_h = .112

    for x, w, header in zip(col_x, widths, headers):
        ax.add_patch(plt.Rectangle((x, y_top), w, .045, transform=ax.transAxes,
                                   facecolor="#EAEAEA", edgecolor="0.55", linewidth=.8))
        ax.text(x + .012, y_top + .023, header, transform=ax.transAxes,
                ha="left", va="center", fontsize=10, fontweight="bold")

    for ri, row in enumerate(rows):
        y = y_top - (ri + 1) * row_h
        shade = "#FFFFFF" if ri % 2 == 0 else "#F7F7F7"
        for x, w, nchars, text in zip(col_x, widths, wrap_chars, row):
            ax.add_patch(plt.Rectangle((x, y), w, row_h, transform=ax.transAxes,
                                       facecolor=shade, edgecolor="0.78", linewidth=.6))
            wrapped = textwrap.fill(text, width=nchars)
            ax.text(x + .012, y + row_h - .023, wrapped, transform=ax.transAxes,
                    ha="left", va="top", fontsize=8.3, linespacing=1.18)

    fig.text(.06, .115,
             "Bar graphs: bars = group mean +/- SEM; dots = mouse-level means. "
             "Previous difficulty and previous outcome are shown on separate slides so the carryover question stays clear.",
             ha="left", va="center", fontsize=9.5, color="0.25")
    fig.text(.06, .08,
             "Important: these are conditional next-trial summaries, not overall session averages.",
             ha="left", va="center", fontsize=9.5, color="0.25", fontweight="bold")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_feedback_detail_metric(ax, project, tp, sex, feedback_animal, col, label, percent):
    d = feedback_animal[(feedback_animal["Project"] == project) &
                        (pd.to_numeric(feedback_animal["Timepoint_Months"], errors="coerce") == tp) &
                        (feedback_animal["Sex"] == sex)].copy()
    if d.empty or "Previous_Outcome_Detail" not in d.columns or col not in d.columns:
        ax.axis("off")
        return
    cats = ["Hit", "Correct Rejection", "Miss", "False Alarm"]
    cats = [c for c in cats if c in set(d["Previous_Outcome_Detail"].dropna().astype(str))]
    if not cats:
        ax.axis("off")
        return
    labels = {"Hit": "After Hit", "Correct Rejection": "After CR", "Miss": "After Miss", "False Alarm": "After FA"}
    colors = group_color_map(project)
    groups = [g for g in GROUP_ORDER[project] if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    offsets = np.linspace(-.27, .27, max(1, len(groups)))
    width = .14 if len(groups) >= 4 else .18
    centers = np.arange(len(cats), dtype=float)
    allvals = []
    for gi, (geno, trt) in enumerate(groups):
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        means, errors = [], []
        xpos = centers + offsets[gi]
        for ci, cat in enumerate(cats):
            cell = gd[gd["Previous_Outcome_Detail"].astype(str) == cat][["Animal_ID", col]].dropna()
            if not cell.empty:
                cell = cell.groupby("Animal_ID", as_index=False)[col].mean()
                s = metric_values(cell[col], percent).dropna()
            else:
                s = pd.Series(dtype=float)
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            if not s.empty:
                jitter = np.linspace(-.025, .025, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), xpos[ci]) + jitter, s, s=11, color=colors[(geno, trt)],
                           edgecolors="white", linewidths=.3, zorder=4)
                allvals.extend(s.tolist())
            if np.isfinite(means[-1]):
                allvals += [means[-1] - errors[-1], means[-1] + errors[-1]]
        ax.bar(xpos, means, width=width, color=colors[(geno, trt)], alpha=.58,
               edgecolor="0.35", linewidth=.6, zorder=2)
        ax.errorbar(xpos, means, yerr=errors, fmt="none", ecolor="0.20",
                    elinewidth=1.0, capsize=2.5, capthick=1.0, zorder=7)
    ax.set_xticks(centers)
    informative_labels = {
        "Hit": "After Hit\n(prev touch, correct)",
        "Correct Rejection": "After CR\n(prev withhold, correct)",
        "Miss": "After Miss\n(prev withhold, error)",
        "False Alarm": "After FA\n(prev touch, error)",
    }
    ax.set_xticklabels([informative_labels.get(c, labels[c]) for c in cats], fontsize=7.2)
    ax.set_ylabel(label, fontsize=9, fontweight="bold", labelpad=8)
    ax.set_title(f"{sex}: {label}", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(axis="y", alpha=.20)
    ax.tick_params(axis="both", labelsize=8)
    apply_smart_ylim(ax, allvals, percent)


def feedback_detail_combined_pages(pdf, project, tp, feedback_animal):
    if feedback_animal is None or feedback_animal.empty:
        return
    metrics = [
        ("Hit_Rate", "Next-trial hit rate (%)", True),
        ("False_Alarm_Rate", "Next-trial false alarm rate (%)", True),
        ("Mean_Session_Correct_Touch_Latency_s", "Next correct latency (s)", False),
        ("Mean_Session_Incorrect_Touch_Latency_s", "Next incorrect latency (s)", False),
        ("Mean_Session_Reward_Retrieval_Latency_s", "Next reward latency (s)", False),
    ]
    chunks = [metrics[i:i+2] for i in range(0, len(metrics), 2)]
    for page_i, chunk in enumerate(chunks, start=1):
        fig, axes = plt.subplots(len(chunk), 2, figsize=(16, 9), squeeze=False)
        fig.suptitle(f"{project} - {tp} months: detailed next-trial behavior by previous outcome ({page_i}/{len(chunks)})",
                     fontsize=18, fontweight="bold", y=.985)
        for r, (col, label, pct) in enumerate(chunk):
            row_axes = []
            for c, sex in enumerate(SEXES):
                ax = axes[r, c]
                _plot_feedback_detail_metric(ax, project, tp, sex, feedback_animal, col, label, pct)
                row_axes.append(ax)
            sync_y_limits(row_axes)
        count_df = feedback_animal[(feedback_animal["Project"] == project) &
                                   (pd.to_numeric(feedback_animal["Timepoint_Months"], errors="coerce") == tp)].copy()
        combined_group_legend(fig, project, count_df, y=.047, fontsize=8.3)
        fig.text(.5, .012,
                 "Previous trial is separated into Hit, Correct Rejection, Miss and False Alarm. "
                 "These are conditional next-trial summaries; dots are mouse-level means.",
                 ha="center", fontsize=8.1)
        fig.tight_layout(rect=[.02, .16, .98, .94])
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def _plot_response_stay_metric(ax, project, tp, sex, stimulus, transition_animal):
    d = transition_animal[(transition_animal["Project"] == project) &
                          (pd.to_numeric(transition_animal["Timepoint_Months"], errors="coerce") == tp) &
                          (transition_animal["Sex"] == sex) &
                          (transition_animal["Next_Stimulus_Class"] == stimulus)].copy()
    if d.empty:
        ax.axis("off")
        return
    cats = ["Hit", "Correct Rejection", "Miss", "False Alarm"]
    cats = [c for c in cats if c in set(d["Previous_Outcome_Detail"].dropna().astype(str))]
    colors = group_color_map(project)
    groups = [g for g in GROUP_ORDER[project] if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    offsets = np.linspace(-.27, .27, max(1, len(groups)))
    centers = np.arange(len(cats), dtype=float)
    labels = {"Hit": "After Hit", "Correct Rejection": "After CR", "Miss": "After Miss", "False Alarm": "After FA"}
    allvals = []
    for gi, (geno, trt) in enumerate(groups):
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        xpos = centers + offsets[gi]
        means, errors = [], []
        for ci, cat in enumerate(cats):
            cell = gd[gd["Previous_Outcome_Detail"].astype(str) == cat][["Animal_ID", "Response_Stay_Rate"]].dropna()
            if not cell.empty:
                cell = cell.groupby("Animal_ID", as_index=False)["Response_Stay_Rate"].mean()
                s = metric_values(cell["Response_Stay_Rate"], True).dropna()
            else:
                s = pd.Series(dtype=float)
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            if not s.empty:
                jitter = np.linspace(-.025, .025, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), xpos[ci]) + jitter, s, s=11, color=colors[(geno, trt)],
                           edgecolors="white", linewidths=.3, zorder=4)
                allvals.extend(s.tolist())
        ax.bar(xpos, means, width=.14, color=colors[(geno, trt)], alpha=.58,
               edgecolor="0.35", linewidth=.6, zorder=2)
        ax.errorbar(xpos, means, yerr=errors, fmt="none", ecolor="0.20",
                    elinewidth=1.0, capsize=2.5, capthick=1.0, zorder=7)
    ax.axhline(50, color="0.55", linestyle="--", linewidth=.8, alpha=.65)
    ax.set_xticks(centers)
    ax.set_xticklabels([labels[c] for c in cats], fontsize=7.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Response-stay rate (%)", fontsize=9, fontweight="bold")
    ax.set_title(f"{sex}: next {stimulus.lower()} trial", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(axis="y", alpha=.20)
    ax.tick_params(axis="both", labelsize=8)


def response_stay_combined_page(pdf, project, tp, transition_animal):
    if transition_animal is None or transition_animal.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(16, 9), squeeze=False)
    fig.suptitle(f"{project} - {tp} months: response-stay / response-shift after previous outcome",
                 fontsize=18, fontweight="bold", y=.985)
    for r, stim in enumerate(["Target", "Non-target"]):
        row_axes = []
        for c, sex in enumerate(SEXES):
            ax = axes[r, c]
            _plot_response_stay_metric(ax, project, tp, sex, stim, transition_animal)
            row_axes.append(ax)
        sync_y_limits(row_axes)
    count_df = transition_animal[(transition_animal["Project"] == project) &
                                 (pd.to_numeric(transition_animal["Timepoint_Months"], errors="coerce") == tp)].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.3)
    fig.text(.5, .012,
             "Stay = repeat the previous motor response; shift = switch it. "
             "Hit/FA = previous touch; CR/Miss = previous withhold. "
             "Target and non-target next trials are separated because the same repeated response can be appropriate or inappropriate depending on the next stimulus.",
             ha="center", fontsize=8.0)
    fig.tight_layout(rect=[.02, .16, .98, .94])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def feedback_explainer_page(pdf, project, tp):
    """Cover / interpretation page for the Response Behavior PDF."""
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis("off")

    fig.text(.5, .925, f"{project} - {tp} months: response behavior",
             ha="center", fontsize=23, fontweight="bold")
    fig.text(.5, .875,
             "How previous action and outcome influence the mouse's response on the next standard CPT trial",
             ha="center", fontsize=12.5, color="0.25")

    # Key definitions
    ax.text(.06, .79, "Previous-trial outcome", transform=ax.transAxes,
            fontsize=13, fontweight="bold")
    rows = [
        ("Hit", "Touch", "Correct / rewarded"),
        ("Correct Rejection (CR)", "Withhold", "Correct"),
        ("Miss", "Withhold", "Error"),
        ("False Alarm (FA)", "Touch", "Error"),
    ]
    y = .735
    for outcome, action, valence in rows:
        ax.text(.075, y, outcome, transform=ax.transAxes, fontsize=11.2, fontweight="bold")
        ax.text(.245, y, f"previous action: {action}", transform=ax.transAxes, fontsize=11.2)
        ax.text(.44, y, valence, transform=ax.transAxes, fontsize=11.2)
        y -= .055

    # Stay / shift definition
    ax.text(.06, .49, "Response-stay / response-shift", transform=ax.transAxes,
            fontsize=13, fontweight="bold")
    ax.text(.075, .445,
            "Stay = repeat the previous motor action (touch -> touch, or withhold -> withhold).",
            transform=ax.transAxes, fontsize=11.2)
    ax.text(.075, .405,
            "Shift = switch the previous motor action (touch -> withhold, or withhold -> touch).",
            transform=ax.transAxes, fontsize=11.2)

    # Interpretation logic
    ax.text(.06, .33, "How to interpret the plots", transform=ax.transAxes,
            fontsize=13, fontweight="bold")
    interp = (
        "The same stay response is not always good or bad, so next target and next non-target trials are shown separately. "
        "The most informative feedback contrasts hold the previous motor action constant: "
        "Hit vs FA compares two previous touches (correct vs error), while CR vs Miss compares two previous withholds (correct vs error). "
        "Differences between those pairs suggest outcome/feedback is modifying response persistence beyond simple motor repetition."
    )
    ax.text(.075, .285, interp, transform=ax.transAxes, ha="left", va="top",
            fontsize=10.8, linespacing=1.35, wrap=True)

    ax.text(.06, .13, "Important:", transform=ax.transAxes,
            fontsize=11.5, fontweight="bold")
    ax.text(.135, .13,
            "This is a CPT analogue of response persistence / shifting, not classic PRL win-stay / lose-shift.",
            transform=ax.transAxes, fontsize=10.8)

    fig.text(.5, .055,
             "Correction trials are excluded from the response-transition sequence; the next trial means the next ordinary mixed-SD Probe 2b presentation.",
             ha="center", fontsize=9.3, color="0.30")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def baseline_probe_page(pdf, project, tp, sex, stage4_animal, probe_animal):
    base = stage4_animal[
        (stage4_animal["Project"] == project) &
        (stage4_animal["Timepoint_Months"] == tp) &
        (stage4_animal["Sex"] == sex)
    ].copy()
    probe = probe_animal[
        (probe_animal["Project"] == project) &
        (probe_animal["Timepoint_Months"] == tp) &
        (probe_animal["Sex"] == sex)
    ].copy()

    if base.empty or probe.empty:
        return

    styles = group_style_map(project)
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: Stage 4 baseline -> Probe 2b",
                 fontsize=20, fontweight="bold", y=.985)

    # Deliberate spacing between baseline and mixed-SD Probe 2b.
    x_stage = 0.0
    x_probe = np.array([1.45, 2.45, 3.45, 4.45])
    xticks = [x_stage] + list(x_probe)
    xlabels = ["Stage 4", "2.0", "1.0", "0.5", "0.2"]

    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        allvals = []
        for geno, trt in GROUP_ORDER[project]:
            gb = base[(base["Genotype"] == geno) & (base["Treatment"] == trt)]
            gp = probe[(probe["Genotype"] == geno) & (probe["Treatment"] == trt)]
            if gb.empty or gp.empty:
                continue

            st = styles[(geno, trt)]
            n = len(set(gb["Animal_ID"]).intersection(set(gp["Animal_ID"])))

            s0 = metric_values(gb[col], percent).dropna()
            if not s0.empty:
                bmean, berr = float(s0.mean()), sem(s0)
                ax.errorbar([x_stage], [bmean], yerr=[berr], marker="o", markersize=5, capsize=3,
                            color=st["color"], linestyle="none",
                            label=f"{geno} | {trt} (n={n})")
                allvals.extend([bmean + berr, bmean - berr])

            px, py, pe = [], [], []
            for x, dur in zip(x_probe, DURS):
                s = metric_values(gp.loc[np.isclose(gp["Stimulus_Duration_s"], dur), col], percent).dropna()
                if s.empty:
                    continue
                px.append(x); py.append(float(s.mean())); pe.append(sem(s))
            if px:
                # Probe-only line starts at 2.0 s; no connecting line from Stage 4.
                ax.errorbar(px, py, yerr=pe, marker="o", markersize=5, capsize=3,
                            color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"])
                allvals.extend(np.array(py) + np.array(pe))
                allvals.extend(np.array(py) - np.array(pe))

        # Faint separator reinforces baseline vs mixed-SD Probe 2b.
        ax.axvline(0.72, color="0.65", linestyle="--", linewidth=.8, alpha=.65)
        ax.text(.115, .03, "Baseline", transform=ax.transAxes, ha="center", va="bottom",
                fontsize=7.5, color="0.35")
        ax.text(.64, .03, "Mixed-SD Probe 2b", transform=ax.transAxes, ha="center", va="bottom",
                fontsize=7.5, color="0.35")

        ax.set_xticks(xticks)
        ax.set_xticklabels(xlabels)
        ax.set_xlim(-.30, 4.75)
        ax.set_xlabel("", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(label, fontsize=10, fontweight="bold")
        add_sex_watermark(ax, sex)
        ax.grid(alpha=.20)
        ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, allvals, percent)

    axes.flat[7].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    # De-duplicate legend labels introduced by baseline-only plotting.
    unique = {}
    for h, lab in zip(handles, labels):
        unique.setdefault(lab, h)
    legend_bottom(fig, list(unique.values()), list(unique.keys()), ncol=2, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Stage 4 is visually separated from the mixed-SD Probe 2b sequence. Solid = treated; dotted = control.",
             ha="center", fontsize=8.4)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def _resolve_metric_column(df, canonical):
    """Return the available column matching a graph metric, including extractor aliases."""
    aliases = {
        "Hit_Rate": ["Hit_Rate", "HR", "HitRate", "hit_rate"],
        "False_Alarm_Rate": ["False_Alarm_Rate", "FAR", "FalseAlarmRate", "false_alarm_rate"],
        "d_prime": ["d_prime", "dprime", "D_Prime", "DPrime", "d'"],
        "criterion_c": ["criterion_c", "c", "Response_Bias", "Response_Bias_c", "Criterion"],
        "Mean_Session_Correct_Touch_Latency_s": [
            "Mean_Session_Correct_Touch_Latency_s", "Mean_Correct_Touch_Latency_s",
            "Correct_Touch_Latency", "Correct_Touch_Latency_s", "CorrectTouchLatency",
            "Correct_Touch_Latency_AnalysisClean_s", "Mean Correct Touch Latency",
            "AVG_Average - Correct Choice Latency"
        ],
        "Mean_Session_Incorrect_Touch_Latency_s": [
            "Mean_Session_Incorrect_Touch_Latency_s", "Mean_Incorrect_Touch_Latency_s",
            "Incorrect_Touch_Latency", "Incorrect_Touch_Latency_s", "IncorrectTouchLatency",
            "Incorrect_Touch_Latency_AnalysisClean_s", "Mean Incorrect Touch Latency",
            "AVG_Average - Mistake Latency"
        ],
        "Mean_Session_Reward_Retrieval_Latency_s": [
            "Mean_Session_Reward_Retrieval_Latency_s", "Mean_Reward_Retrieval_Latency_s",
            "Reward_Retrieval_Latency", "Reward_Retrieval_Latency_s", "RewardRetrievalLatency",
            "Reward_Retrieval_Latency_AnalysisClean_s", "Mean Reward Retrieval Latency",
            "AVG_Average - Reward Retrieval Latency"
        ],
    }
    return first_present(df, aliases.get(canonical, [canonical]))

def _plot_stage4_probe_metric(ax, project, tp, sex, col, label, percent, stage4_animal, probe_animal):
    base = stage4_animal[
        (stage4_animal["Project"] == project) &
        (stage4_animal["Timepoint_Months"] == tp) &
        (stage4_animal["Sex"] == sex)
    ].copy()
    probe = probe_animal[
        (probe_animal["Project"] == project) &
        (probe_animal["Timepoint_Months"] == tp) &
        (probe_animal["Sex"] == sex)
    ].copy()
    if base.empty or probe.empty:
        ax.axis("off")
        return [], []

    styles = group_style_map(project)
    x_stage = 0.0
    x_probe = np.array([1.45, 2.45, 3.45, 4.45])
    xticks = [x_stage] + list(x_probe)
    xlabels = ["Stage 4", "2.0", "1.0", "0.5", "0.2"]
    allvals = []

    base_metric_col = _resolve_metric_column(base, col)
    probe_metric_col = _resolve_metric_column(probe, col)

    for geno, trt in GROUP_ORDER[project]:
        gb = base[(base["Genotype"] == geno) & (base["Treatment"] == trt)]
        gp = probe[(probe["Genotype"] == geno) & (probe["Treatment"] == trt)]
        if gb.empty or gp.empty:
            continue
        st = styles[(geno, trt)]
        n = len(set(gb["Animal_ID"].astype(str)).intersection(set(gp["Animal_ID"].astype(str))))

        # Stage-4 exports are not perfectly consistent about latency column names.
        # If a baseline metric is unavailable, keep building the PDF and plot the
        # Probe data instead of stopping the entire graph run with a KeyError.
        s0 = metric_values(gb[base_metric_col], percent).dropna() if base_metric_col else pd.Series(dtype=float)
        if not s0.empty:
            bmean, berr = float(s0.mean()), sem(s0)
            ax.errorbar([x_stage], [bmean], yerr=[berr], marker="o", markersize=5, capsize=3,
                        color=st["color"], linestyle="none", label=f"{geno} | {trt} (n={n})")
            allvals.extend([bmean + berr, bmean - berr])

        px, py, pe = [], [], []
        if probe_metric_col:
            for x, dur in zip(x_probe, DURS):
                svals = metric_values(
                    gp.loc[np.isclose(gp["Stimulus_Duration_s"], dur), probe_metric_col], percent
                ).dropna()
                if svals.empty:
                    continue
                px.append(x)
                py.append(float(svals.mean()))
                pe.append(sem(svals))
        if px:
            ax.errorbar(px, py, yerr=pe, marker="o", markersize=5, capsize=3,
                        color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"])
            allvals.extend(np.array(py) + np.array(pe))
            allvals.extend(np.array(py) - np.array(pe))

    if base_metric_col is None:
        ax.text(.02, .96, "Stage 4 metric unavailable in baseline CSV",
                transform=ax.transAxes, ha="left", va="top", fontsize=6.8, color="0.45")
    if probe_metric_col is None:
        ax.text(.98, .96, "Probe metric unavailable",
                transform=ax.transAxes, ha="right", va="top", fontsize=6.8, color="0.45")

    ax.axvline(0.72, color="0.65", linestyle="--", linewidth=.8, alpha=.65)
    ax.text(.115, .03, "Baseline", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=7.5, color="0.35")
    ax.text(.64, .03, "Mixed-SD Probe 2b", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=7.5, color="0.35")
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_xlim(-.30, 4.75)
    ax.set_xlabel("", fontsize=8)
    ax.set_ylabel(label, fontsize=8)
    ax.set_title(f"{sex}: {label}", fontsize=10, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(alpha=.20)
    ax.tick_params(labelsize=8)
    apply_smart_ylim(ax, allvals, percent)
    return ax.get_legend_handles_labels()

def stage4_probe_combined_page(pdf, project, tp, stage4_animal, probe_animal, page_kind):
    if page_kind == "rates":
        metrics = [
            ("Hit_Rate", "Hit rate (%)", True),
            ("False_Alarm_Rate", "False alarm rate (%)", True),
        ]
        title = "Hit rate and false alarm rate"
    elif page_kind == "signal":
        metrics = [
            ("d_prime", "d′", False),
            ("criterion_c", "Response bias (c)", False),
        ]
        title = "d prime and response bias"
    else:
        metrics = STORY_LATENCY_METRICS
        title = "Correct and reward retrieval latencies"

    fig, axes = plt.subplots(2, 2, figsize=(13.333, 7.5))
    fig.suptitle(f"{project} - {tp} months: Stage 4 baseline -> Probe 2b - {title}",
                 fontsize=20, fontweight="bold", y=.985)
    for row, (col, label, percent) in enumerate(metrics):
        for col_idx, sex in enumerate(SEXES):
            _plot_stage4_probe_metric(
                axes[row, col_idx], project, tp, sex, col, label, percent, stage4_animal, probe_animal
            )
    count_df = probe_animal[
        (probe_animal["Project"] == project) &
        (probe_animal["Timepoint_Months"] == tp)
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Female panels are on the left; male panels are on the right. Solid = treated; dotted = control.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .94])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def _plot_timepoint_metric_by_duration(ax, project, dur, sex, col, label, percent, animal):
    d = animal[
        (animal["Project"] == project) &
        (animal["Sex"] == sex) &
        (np.isclose(animal["Stimulus_Duration_s"], dur))
    ].copy()
    if d.empty:
        ax.axis("off")
        return [], []
    styles = group_style_map(project)
    allvals = []
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty:
            continue
        av = gd.groupby(["Animal_ID", "Timepoint_Months"], as_index=False)[col].mean()
        xs, ys, es = [], [], []
        for tp in TPS:
            s = metric_values(av.loc[av["Timepoint_Months"] == tp, col], percent).dropna()
            if s.empty:
                continue
            xs.append(tp)
            ys.append(float(s.mean()))
            es.append(sem(s))
        if not xs:
            continue
        st = styles[(geno, trt)]
        ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3,
                    color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                    label=f"{geno} | {trt} (n={av['Animal_ID'].nunique()})")
        allvals.extend(np.array(ys) + np.array(es))
        allvals.extend(np.array(ys) - np.array(es))
    ax.set_xticks(TPS)
    ax.set_xlabel("Age / time point (months)", fontsize=8)
    ax.set_ylabel(label, fontsize=8)
    ax.set_title(f"{sex}: {dur:g}s {label}", fontsize=10, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(alpha=.20)
    ax.tick_params(labelsize=8)
    apply_smart_ylim(ax, allvals, percent)
    return ax.get_legend_handles_labels()

def timepoint_duration_comparison_page(pdf, project, animal, dur, page_kind):
    if page_kind == "rates":
        metrics = [
            ("Hit_Rate", "Hit rate (%)", True),
            ("False_Alarm_Rate", "False alarm rate (%)", True),
        ]
        title = "Hit rate and false alarm rate"
    elif page_kind == "signal":
        metrics = [
            ("d_prime", "d′", False),
            ("criterion_c", "Response bias (c)", False),
        ]
        title = "d prime and response bias"
    else:
        metrics = STORY_LATENCY_METRICS
        title = "Correct and reward retrieval latencies"

    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    fig.suptitle(f"{project} - {dur:g}s Probe 2b across 6 / 9 / 12 months - {title}",
                 fontsize=20, fontweight="bold", y=.985)
    for row, (col, label, percent) in enumerate(metrics):
        for col_idx, sex in enumerate(SEXES):
            _plot_timepoint_metric_by_duration(
                axes[row, col_idx], project, dur, sex, col, label, percent, animal
            )
    count_df = animal[
        (animal["Project"] == project) &
        (np.isclose(animal["Stimulus_Duration_s"], dur))
    ].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Female panels are on the left; male panels are on the right. X-axis is age/time point.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .94])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def _plot_iti_metric_by_sd(ax, project, tp, sex, iti_data, col, label, percent, iti=None):
    d = iti_data[
        (iti_data["Project"] == project) &
        (iti_data["Timepoint_Months"] == tp) &
        (iti_data["Sex"] == sex)
    ].copy()
    if iti is not None and "Current_ITI_s" in d.columns:
        d = d[np.isclose(pd.to_numeric(d["Current_ITI_s"], errors="coerce"), float(iti))].copy()
    if d.empty or col not in d.columns:
        ax.axis("off")
        return
    styles = group_style_map(project)
    vals = []
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty:
            continue
        av = gd.groupby(["Animal_ID", "Stimulus_Duration_s"], as_index=False)[col].mean()
        xs, ys, es = [], [], []
        for di, dur in enumerate(DURS):
            s = metric_values(av.loc[np.isclose(av["Stimulus_Duration_s"], dur), col], percent).dropna()
            if s.empty:
                continue
            xs.append(di); ys.append(float(s.mean())); es.append(sem(s))
        if not xs:
            continue
        st = styles[(geno, trt)]
        ax.errorbar(xs, ys, yerr=es, marker="o", markersize=4.5,
                    capsize=2.6, color=st["color"],
                    linestyle=st["linestyle"], linewidth=st["linewidth"],
                    label=f"{geno} | {trt}")
        vals.extend(np.array(ys) + np.array(es))
        vals.extend(np.array(ys) - np.array(es))
    ax.set_xticks(range(len(DURS)))
    ax.set_xticklabels([dur_label(x) for x in DURS])
    ax.set_xlabel("Stimulus duration", fontsize=8)
    ax.set_ylabel(label, fontsize=8)
    iti_title = f" - {int(iti)}s ITI" if iti is not None else ""
    ax.set_title(f"{sex}{iti_title}", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(alpha=.20)
    ax.tick_params(labelsize=8)
    apply_smart_ylim(ax, vals, percent)

def iti_metric_page(pdf, project, tp, iti_data, page_kind):
    if page_kind == "signal":
        metrics = [("d_prime", "d prime", False), ("criterion_c", "Response bias (c)", False)]
        title = "d prime and response bias by 2s vs 3s ITI"
    elif page_kind == "rates":
        metrics = [("Hit_Rate", "Hit rate (%)", True), ("False_Alarm_Rate", "False alarm rate (%)", True)]
        title = "Hit rate and false alarm rate by 2s vs 3s ITI"
    else:
        metrics = [
            ("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
            ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False),
        ]
        title = "Latencies by 2s vs 3s ITI"
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months: {title}", fontsize=19, fontweight="bold", y=.985)
    for row, (col, label, percent) in enumerate(metrics):
        for col_idx, (sex, iti) in enumerate([(SEXES[0], 2), (SEXES[0], 3), (SEXES[1], 2), (SEXES[1], 3)]):
            _plot_iti_metric_by_sd(axes[row, col_idx], project, tp, sex, iti_data, col, label, percent, iti=iti)
        sync_y_limits([axes[row, col_idx] for col_idx in range(4)])
        axes[row, 0].set_ylabel(label, fontsize=8)
        for col_idx in range(1, 4):
            axes[row, col_idx].set_ylabel("")
    count_df = iti_data[(iti_data["Project"] == project) & (iti_data["Timepoint_Months"] == tp)].copy()
    handles, labels = [], []
    styles = group_style_map(project)
    for geno, trt in GROUP_ORDER[project]:
        gd = count_df[(count_df["Genotype"] == geno) & (count_df["Treatment"] == trt)]
        if gd.empty:
            continue
        st = styles[(geno, trt)]
        handles.append(plt.Line2D([0], [0], color=st["color"], linestyle=st["linestyle"],
                                  linewidth=st["linewidth"], marker="o", markersize=5))
        labels.append(sex_n_label(count_df, geno, trt))
    legend_bottom(fig, handles, labels, ncol=2, y=.045, fontsize=8.2)
    fig.text(.5, .012,
             "Each panel shows one sex and one ITI. Each mouse is averaged across Probe 2b sessions 1-4. Correction trials are excluded.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .93])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def _iti_vigilance_average_frame(iti_decile_animal, col):
    if iti_decile_animal.empty or col not in iti_decile_animal.columns:
        return pd.DataFrame()
    idx = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s", "Current_ITI_s"]
    keep = [c for c in idx if c in iti_decile_animal.columns]
    d = iti_decile_animal[keep + [col]].copy()
    d["Current_ITI_s"] = pd.to_numeric(d["Current_ITI_s"], errors="coerce")
    d["Stimulus_Duration_s"] = pd.to_numeric(d["Stimulus_Duration_s"], errors="coerce")
    d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d[d["Current_ITI_s"].isin([2, 3])].dropna(subset=[col]).copy()
    if d.empty:
        return pd.DataFrame()
    return d.groupby(idx, as_index=False, dropna=False)[col].mean()

def _plot_iti_vigilance_average_metric(ax, project, tp, sex, dur, iti_decile_animal, col, label, percent):
    av = _iti_vigilance_average_frame(iti_decile_animal, col)
    d = av[
        (av["Project"] == project) &
        (pd.to_numeric(av["Timepoint_Months"], errors="coerce") == tp) &
        (av["Sex"] == sex) &
        (np.isclose(pd.to_numeric(av["Stimulus_Duration_s"], errors="coerce"), dur))
    ].copy()
    if d.empty:
        ax.axis("off")
        return
    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    if not group_present:
        ax.axis("off")
        return
    centers = np.arange(len(group_present), dtype=float)
    width = .28
    iti_offsets = {2: -width / 2, 3: width / 2}
    vals = []
    for gi, (geno, trt) in enumerate(group_present):
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)].copy()
        if gd.empty:
            continue
        wide = gd.pivot_table(index="Animal_ID", columns="Current_ITI_s", values=col, aggfunc="mean")
        animal_order = [str(a) for a in list(wide.index)]
        jitter_map = {}
        if animal_order:
            jitters = np.linspace(-width * .18, width * .18, len(animal_order)) if len(animal_order) > 1 else np.array([0.0])
            jitter_map = dict(zip(animal_order, jitters))
        for animal_id, row in wide.iterrows():
            if 2 in wide.columns and 3 in wide.columns and pd.notna(row.get(2)) and pd.notna(row.get(3)):
                y2 = metric_values(pd.Series([row.get(2)]), percent).iloc[0]
                y3 = metric_values(pd.Series([row.get(3)]), percent).iloc[0]
                j = jitter_map.get(str(animal_id), 0.0)
                ax.plot([centers[gi] + iti_offsets[2] + j, centers[gi] + iti_offsets[3] + j],
                        [y2, y3], color="0.70", linewidth=.65, alpha=.55, zorder=3)
        for iti in [2, 3]:
            point_df = gd[np.isclose(gd["Current_ITI_s"], iti)].copy()
            point_df["_plot_value"] = metric_values(point_df[col], percent)
            point_df = point_df.dropna(subset=["_plot_value"])
            s = point_df["_plot_value"]
            if s.empty:
                continue
            xpos = centers[gi] + iti_offsets[iti]
            mean, err = float(s.mean()), sem(s)
            ax.bar([xpos], [mean], width=width, color=colors[(geno, trt)],
                   alpha=.34 if iti == 2 else .68, hatch="//" if iti == 2 else None,
                   edgecolor="0.35", linewidth=.65, zorder=2)
            ax.errorbar([xpos], [mean], yerr=[err], fmt="none", ecolor="0.20",
                        elinewidth=.95, capsize=2.4, capthick=.95, zorder=6)
            jitters = [jitter_map.get(str(a), 0.0) for a in point_df["Animal_ID"].tolist()]
            ax.scatter(np.full(len(point_df), xpos) + np.array(jitters), point_df["_plot_value"], s=12,
                       color=colors[(geno, trt)], edgecolors="white",
                       linewidths=.30, alpha=.90, zorder=7)
            vals.extend(s.tolist())
            vals.extend([mean + err, mean - err])
    ax.set_xticks(centers)
    ax.set_xticklabels([f"{g}\n{t}" for g, t in group_present], fontsize=6.8)
    ax.set_xlabel("Within each group: left bar = 2s ITI; right bar = 3s ITI", fontsize=7)
    ax.set_ylabel(label, fontsize=8)
    ax.set_title(f"{sex}: {dur:g}s SD", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(axis="y", alpha=.20)
    ax.tick_params(labelsize=7.5)
    apply_smart_ylim(ax, vals, percent)

def iti_vigilance_average_page(pdf, project, tp, iti_decile_animal, page_kind):
    if iti_decile_animal.empty:
        return
    if page_kind == "rates":
        metrics = [("Hit_Rate", "Hit rate (%)", True),
                   ("False_Alarm_Rate", "False alarm rate (%)", True)]
        title = "D1-D10 average vigilance rates - 2s vs 3s ITI"
    elif page_kind == "signal":
        metrics = [("d_prime", "d prime", False),
                   ("criterion_c", "Response bias (c)", False)]
        title = "D1-D10 average vigilance signal detection - 2s vs 3s ITI"
    else:
        metrics = [("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
                   ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False)]
        title = "D1-D10 average vigilance latencies - 2s vs 3s ITI"
    for col, label, percent in metrics:
        for dur_chunk in [DURS[:2], DURS[2:]]:
            fig, axes = plt.subplots(2, 2, figsize=(16, 9))
            dur_title = " & ".join(f"{d:g}s SD" for d in dur_chunk)
            fig.suptitle(f"{project} - {tp} months: {title} - {label} - {dur_title}",
                         fontsize=18, fontweight="bold", y=.985)
            for row_i, dur in enumerate(dur_chunk):
                for col_i, sex in enumerate(SEXES):
                    _plot_iti_vigilance_average_metric(
                        axes[row_i, col_i], project, tp, sex, dur, iti_decile_animal, col, label, percent
                    )
            sync_y_limits([axes[row_i, col_i] for row_i in range(2) for col_i in range(2)])
            count_df = iti_decile_animal[
                (iti_decile_animal["Project"] == project) &
                (pd.to_numeric(iti_decile_animal["Timepoint_Months"], errors="coerce") == tp)
            ].copy()
            combined_group_legend(fig, project, count_df, y=.047, fontsize=8.4)
            fig.text(.5, .012,
                     "Bars = group mean +/- SEM after averaging each mouse across D1-D10 deciles. Dots = individual mice. Within each group, left bar = 2s ITI and right bar = 3s ITI. Grey lines connect paired mouse values when both ITIs are present.",
                     ha="center", fontsize=8.1)
            fig.tight_layout(rect=[.02, .16, .98, .94])
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

def _iti_delta_whole_frame(iti_data, col):
    idx = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s"]
    empty_cols = idx + ["ITI_Delta_3s_minus_2s"]
    if iti_data.empty or col not in iti_data.columns:
        return pd.DataFrame(columns=empty_cols)
    missing = [c for c in idx + ["Current_ITI_s"] if c not in iti_data.columns]
    if missing:
        return pd.DataFrame(columns=empty_cols)
    d = iti_data[idx + ["Current_ITI_s", col]].copy()
    d["Current_ITI_s"] = pd.to_numeric(d["Current_ITI_s"], errors="coerce")
    wide = d.pivot_table(index=idx, columns="Current_ITI_s", values=col, aggfunc="mean").reset_index()
    if 2 not in wide.columns or 3 not in wide.columns:
        return pd.DataFrame(columns=empty_cols)
    wide["ITI_Delta_3s_minus_2s"] = pd.to_numeric(wide[3], errors="coerce") - pd.to_numeric(wide[2], errors="coerce")
    return wide

def _plot_iti_delta_metric(ax, project, tp, sex, iti_data, col, label, percent, dur=None):
    delta = _iti_delta_whole_frame(iti_data, col)
    if delta.empty or "Project" not in delta.columns:
        ax.axis("off")
        return
    d = delta[(delta["Project"] == project) & (delta["Timepoint_Months"] == tp) & (delta["Sex"] == sex)].copy()
    if dur is not None:
        d = d[np.isclose(pd.to_numeric(d["Stimulus_Duration_s"], errors="coerce"), float(dur))].copy()
    if d.empty:
        ax.axis("off")
        return
    colors = group_color_map(project)
    vals = []
    group_present = [g for g in GROUP_ORDER[project]
                     if not d[(d["Genotype"] == g[0]) & (d["Treatment"] == g[1])].empty]
    if not group_present:
        ax.axis("off")
        return
    if dur is None:
        centers = np.arange(len(DURS), dtype=float)
        width = min(.18, .74 / max(1, len(group_present)))
        offsets = (np.arange(len(group_present)) - (len(group_present) - 1) / 2) * width
    else:
        centers = np.arange(len(group_present), dtype=float)
        width = .56
    for gi, (geno, trt) in enumerate(group_present):
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty:
            continue
        xs, ys, es = [], [], []
        plot_durs = DURS if dur is None else [dur]
        for di, this_dur in enumerate(plot_durs):
            s = pd.to_numeric(gd.loc[np.isclose(gd["Stimulus_Duration_s"], this_dur), "ITI_Delta_3s_minus_2s"], errors="coerce").dropna()
            if percent:
                s = s * 100.0
            if s.empty:
                continue
            xpos = (centers[di] + offsets[gi]) if dur is None else centers[gi]
            mean, err = float(s.mean()), sem(s)
            xs.append(xpos); ys.append(mean); es.append(err)
            jitter = np.linspace(-width * .20, width * .20, len(s)) if len(s) > 1 else np.array([0.0])
            ax.scatter(np.full(len(s), xpos) + jitter, s, s=12,
                       color=colors[(geno, trt)], edgecolors="white",
                       linewidths=.30, alpha=.88, zorder=5)
            vals.extend(s.tolist())
        if not xs:
            continue
        ax.bar(xs, ys, width=width * .86, color=colors[(geno, trt)], alpha=.56,
               edgecolor="0.35", linewidth=.55, zorder=2, label=f"{geno} | {trt}")
        ax.errorbar(xs, ys, yerr=es, fmt="none", ecolor="0.20",
                    elinewidth=.95, capsize=2.3, capthick=.95, zorder=6)
        vals.extend(np.array(ys) + np.array(es)); vals.extend(np.array(ys) - np.array(es))
    ax.axhline(0, color="#333333", linewidth=1, alpha=.65)
    ax.set_xticks(centers)
    if dur is None:
        ax.set_xticklabels([dur_label(x) for x in DURS])
        ax.set_xlabel("Stimulus duration", fontsize=8)
        title_extra = ""
    else:
        ax.set_xticklabels([f"{g}\n{t}" for g, t in group_present], fontsize=6.8)
        ax.set_xlabel("Group", fontsize=8)
        title_extra = f": {dur:g}s SD"
    ax.set_ylabel(f"Delta: {label}", fontsize=8)
    ax.set_title(f"{sex}{title_extra}", fontsize=9.5, fontweight="bold")
    add_sex_watermark(ax, sex)
    ax.grid(alpha=.20)
    ax.tick_params(labelsize=8)
    apply_iti_delta_ylim(ax, vals)

def iti_delta_page(pdf, project, tp, iti_data, page_kind):
    if page_kind == "signal":
        metrics = [("d_prime", "d prime", False), ("criterion_c", "Response bias (c)", False)]
        title = "ITI delta: d prime and response bias"
    elif page_kind == "rates":
        metrics = [("Hit_Rate", "Hit rate (percentage points)", True), ("False_Alarm_Rate", "False alarm rate (percentage points)", True)]
        title = "ITI delta: hit rate and false alarm rate"
    else:
        metrics = [
            ("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
            ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False),
        ]
        title = "ITI delta: latencies"
    available_metrics = [
        (col, label, percent) for col, label, percent in metrics
        if not _iti_delta_whole_frame(iti_data, col).empty
    ]
    if not available_metrics:
        return
    for dur_chunk in [DURS[:2], DURS[2:]]:
        fig, axes = plt.subplots(2, 4, figsize=(16, 9))
        dur_title = " & ".join(f"{d:g}s SD" for d in dur_chunk)
        fig.suptitle(f"{project} - {tp} months: {title} - {dur_title}",
                     fontsize=19, fontweight="bold", y=.985)
        panel_cols = [(SEXES[0], dur_chunk[0]), (SEXES[0], dur_chunk[1]),
                      (SEXES[1], dur_chunk[0]), (SEXES[1], dur_chunk[1])]
        for row, (col, label, percent) in enumerate(metrics):
            for col_idx, (sex, dur) in enumerate(panel_cols):
                _plot_iti_delta_metric(axes[row, col_idx], project, tp, sex, iti_data, col, label, percent, dur=dur)
            sync_y_limits([axes[row, col_idx] for col_idx in range(4)])
            axes[row, 0].set_ylabel(f"Delta: {label}", fontsize=8)
            for col_idx in range(1, 4):
                axes[row, col_idx].set_ylabel("")
        count_df = iti_data[(iti_data["Project"] == project) & (iti_data["Timepoint_Months"] == tp)].copy()
        combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
        fig.text(.5, .012,
                 "Positive values mean the metric is higher at 3s ITI than 2s ITI. Deltas are paired within mouse before group mean +/- SEM.",
                 ha="center", fontsize=8.5)
        fig.tight_layout(rect=[.02, .16, .98, .93])
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

def iti_dprime_delta_half_page(pdf, project, tp, iti_animal):
    if iti_animal.empty or "d_prime" not in iti_animal.columns:
        return
    idx = ["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
           "Timepoint_Months", "Stimulus_Duration_s", "Session_Half"]
    d = iti_animal[idx + ["Current_ITI_s", "d_prime"]].copy()
    d["Current_ITI_s"] = pd.to_numeric(d["Current_ITI_s"], errors="coerce")
    wide = d.pivot_table(index=idx, columns="Current_ITI_s", values="d_prime", aggfunc="mean").reset_index()
    if 2 not in wide.columns or 3 not in wide.columns:
        return
    wide["dPrime_Delta_3s_minus_2s"] = pd.to_numeric(wide[3], errors="coerce") - pd.to_numeric(wide[2], errors="coerce")
    delta = wide[(wide["Project"] == project) & (wide["Timepoint_Months"] == tp)].copy()
    if delta.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months: d prime ITI effect by session half",
                 fontsize=19, fontweight="bold", y=.985)
    styles = group_style_map(project)
    live_axes = []
    for row, half in enumerate(["First half", "Last half"]):
        for col_idx, sex in enumerate(SEXES):
            ax = axes[row, col_idx]
            q = delta[(delta["Session_Half"] == half) & (delta["Sex"] == sex)].copy()
            if q.empty:
                ax.axis("off")
                continue
            vals = []
            for geno, trt in GROUP_ORDER[project]:
                gd = q[(q["Genotype"] == geno) & (q["Treatment"] == trt)]
                if gd.empty:
                    continue
                xs, ys, es = [], [], []
                for di, dur in enumerate(DURS):
                    s = pd.to_numeric(
                        gd.loc[np.isclose(gd["Stimulus_Duration_s"], dur), "dPrime_Delta_3s_minus_2s"],
                        errors="coerce"
                    ).dropna()
                    if s.empty:
                        continue
                    xs.append(di); ys.append(float(s.mean())); es.append(sem(s))
                if not xs:
                    continue
                st = styles[(geno, trt)]
                ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3,
                            color=st["color"], linestyle=st["linestyle"],
                            linewidth=st["linewidth"], label=f"{geno} | {trt}")
                vals.extend(np.array(ys) + np.array(es))
                vals.extend(np.array(ys) - np.array(es))
            ax.axhline(0, color="#333333", linewidth=1, alpha=.55)
            ax.set_xticks(range(len(DURS)))
            ax.set_xticklabels([dur_label(x) for x in DURS])
            ax.set_xlabel("Stimulus duration", fontsize=8)
            ax.set_ylabel("d prime delta (3s ITI - 2s ITI)", fontsize=8)
            ax.set_title(f"{sex}: {half}", fontsize=10, fontweight="bold")
            add_sex_watermark(ax, sex)
            ax.grid(alpha=.20)
            ax.tick_params(labelsize=8)
            apply_iti_delta_ylim(ax, vals)
            live_axes.append(ax)
    sync_y_limits(live_axes)
    count_df = delta[(delta["Project"] == project) & (delta["Timepoint_Months"] == tp)].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.5)
    fig.text(.5, .012,
             "Positive values mean better sensitivity at 3s ITI than 2s ITI. First/last halves are averaged across Probe 2b sessions 1-4 within mouse.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .93])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def baseline_probe_bar_dot_page(pdf, project, tp, sex, stage4_animal, probe_animal):
    base = stage4_animal[
        (stage4_animal["Project"] == project) &
        (stage4_animal["Timepoint_Months"] == tp) &
        (stage4_animal["Sex"] == sex)
    ].copy()
    probe = probe_animal[
        (probe_animal["Project"] == project) &
        (probe_animal["Timepoint_Months"] == tp) &
        (probe_animal["Sex"] == sex)
    ].copy()
    if base.empty or probe.empty:
        return

    colors = group_color_map(project)
    group_present = [g for g in GROUP_ORDER[project]
                     if not base[(base["Genotype"] == g[0]) & (base["Treatment"] == g[1])].empty
                     and not probe[(probe["Genotype"] == g[0]) & (probe["Treatment"] == g[1])].empty]
    if not group_present:
        return

    x_stage = 0.0
    x_probe = np.array([1.45, 2.45, 3.45, 4.45])
    base_x = np.array([x_stage] + list(x_probe), dtype=float)
    xticks = list(base_x)
    xlabels = ["Stage 4", "2.0", "1.0", "0.5", "0.2"]
    offsets = np.linspace(-.22, .22, max(1, len(group_present)))
    width = .13

    page_sets = [
        ("main measures", MAIN_METRICS, (2, 2)),
        ("latencies", LATENCY_METRICS, (1, 3)),
    ]
    for page_name, metrics, layout in page_sets:
        fig, axes = plt.subplots(*layout, figsize=(16, 9))
        axes = np.atleast_1d(axes).ravel()
        fig.suptitle(
            f"{project} - {tp} months - {sex}: individual values, Stage 4 baseline -> Probe 2b ({page_name})",
            fontsize=19, fontweight="bold", y=.985
        )

        for i, (col, label, percent) in enumerate(metrics):
            ax = axes[i]
            allvals = []
            for gi, (geno, trt) in enumerate(group_present):
                gb = base[(base["Genotype"] == geno) & (base["Treatment"] == trt)]
                gp = probe[(probe["Genotype"] == geno) & (probe["Treatment"] == trt)]
                if gb.empty or gp.empty:
                    continue
                xs = base_x + offsets[gi]
                means, errors = [], []
                cells = [gb] + [gp[np.isclose(gp["Stimulus_Duration_s"], dur)] for dur in DURS]
                for ci, cell in enumerate(cells):
                    vals = cell[["Animal_ID", col]].dropna().copy()
                    vals["PlotValue"] = metric_values(vals[col], percent)
                    s = vals["PlotValue"].dropna()
                    means.append(float(s.mean()) if not s.empty else np.nan)
                    errors.append(sem(s))
                    if s.empty:
                        continue
                    jitter = np.linspace(-.035, .035, len(s)) if len(s) > 1 else np.array([0.0])
                    ax.scatter(np.full(len(s), xs[ci]) + jitter, s, s=14,
                               color=colors[(geno, trt)], edgecolors="white",
                               linewidths=.35, zorder=4)
                    allvals.extend(s.tolist())
                    if np.isfinite(means[-1]):
                        allvals.extend([means[-1] + errors[-1], means[-1] - errors[-1]])

                n = len(set(gb["Animal_ID"].astype(str)).intersection(set(gp["Animal_ID"].astype(str))))
                ax.bar(xs, means, width=width, color=colors[(geno, trt)], alpha=.58,
                       edgecolor="0.35", linewidth=.65,
                       label=f"{geno} | {trt} (n={n})", zorder=2)
                ax.errorbar(xs, means, yerr=errors, fmt="none", ecolor="0.20",
                            elinewidth=1.05, capsize=2.8, capthick=1.05, zorder=7)

            ax.axvline(0.72, color="0.65", linestyle="--", linewidth=.8, alpha=.65)
            ax.text(.115, .03, "Baseline", transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=7.5, color="0.35")
            ax.text(.64, .03, "Mixed-SD Probe 2b", transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=7.5, color="0.35")
            ax.set_xticks(xticks)
            ax.set_xticklabels(xlabels)
            ax.set_xlim(-.30, 4.75)
            ax.set_xlabel("", fontsize=8)
            ax.set_ylabel(label, fontsize=8)
            ax.set_title(label, fontsize=10, fontweight="bold")
            add_sex_watermark(ax, sex)
            ax.grid(axis="y", alpha=.20)
            ax.tick_params(labelsize=8)
            apply_smart_ylim(ax, allvals, percent)

        for ax in axes[len(metrics):]:
            ax.axis("off")
        handles, labels = axes[0].get_legend_handles_labels()
        unique = {}
        for h, lab in zip(handles, labels):
            unique.setdefault(lab, h)
        legend_bottom(fig, list(unique.values()), list(unique.keys()), ncol=2, y=.047, fontsize=8.5)
        fig.text(.5, .012,
                 "Bars = mean +/- SEM; each dot = one mouse. Stage 4 is visually separated from the mixed-SD Probe 2b sequence.",
                 ha="center", fontsize=8.3)
        fig.tight_layout(rect=[.02, .16, .98, .94])
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

def end_summary_timepoints(pdf, project, animal, sex):
    """Sex-specific longitudinal percent-change summary.

    Female and Male are kept separate because the corrected d-prime analysis
    indicates meaningful sex and genotype effects.
    """
    d = animal[(animal["Project"] == project) & (animal["Sex"] == sex)].copy()
    if d.empty:
        return
    styles = group_style_map(project)
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project}: percent change from 6-month Probe 2b baseline - {sex}",
                 fontsize=20, fontweight="bold", y=.985)
    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        vals = []
        for geno, trt in GROUP_ORDER[project]:
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            if gd.empty:
                continue
            av = gd.groupby(["Animal_ID", "Timepoint_Months"], as_index=False)[col].mean()
            wide = av.pivot(index="Animal_ID", columns="Timepoint_Months", values=col)
            if 6 not in wide.columns:
                continue
            xs, ys, es = [], [], []
            for tp in TPS:
                if tp == 6:
                    s = pd.Series(0.0, index=wide[wide[6].notna()].index)
                elif tp in wide.columns:
                    paired = wide[[6, tp]].dropna()
                    base = metric_values(paired[6], percent)
                    follow = metric_values(paired[tp], percent)
                    denom = base.abs().replace(0, np.nan)
                    s = ((follow - base) / denom * 100.0).replace([np.inf, -np.inf], np.nan).dropna()
                else:
                    s = pd.Series(dtype=float)
                if s.empty:
                    continue
                xs.append(tp); ys.append(float(s.mean())); es.append(sem(s))
            st = styles[(geno, trt)]
            ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3,
                        color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                        label=f"{geno} | {trt} (n={wide[6].notna().sum()})")
            vals.extend(np.array(ys) + np.array(es)); vals.extend(np.array(ys) - np.array(es))
        ax.axhline(0, color="0.15", linewidth=1.1, alpha=.85)
        ax.set_xticks(TPS)
        ax.set_xlabel("Age / time point (months)", fontsize=8)
        ax.set_ylabel("% change from 6 months", fontsize=8)
        ax.set_title(f"{label}: % change", fontsize=10, fontweight="bold")
        ax.grid(alpha=.20); ax.tick_params(labelsize=8)
        if vals:
            lo, hi = np.nanpercentile(vals, [2, 98])
            m = max(abs(lo), abs(hi), 10)
            ax.set_ylim(-m * 1.18, m * 1.18)
    axes.flat[7].axis("off")
    count_df = animal[animal["Project"] == project].copy()
    combined_group_legend(fig, project, count_df, y=.047, fontsize=8.7)
    fig.text(.5, .012,
             f"{sex} only. Zero line = no change from each mouse's 6-month value; 9 and 12 months show animal-level percent change before group mean +/- SEM.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .16, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def end_summary_sex(pdf, project, animal):
    # Compare sexes after collapsing genotype, treatment, stimulus duration and time point.
    d = animal[animal["Project"] == project].copy()
    if d.empty:
        return
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project}: brief sex comparison (genotype/treatment/time collapsed)",
                 fontsize=20, fontweight="bold", y=.985)
    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        means, errors, vals = [], [], []
        for sex in SEXES:
            ad = d[d["Sex"] == sex].groupby("Animal_ID", as_index=False)[col].mean()
            s = metric_values(ad[col], percent).dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            vals.extend(s.tolist())
        ax.bar([0, 1], means, yerr=errors, capsize=3, alpha=.55)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["Female", "Male"])
        ax.set_ylabel(label, fontsize=8); ax.set_title(label, fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=.20); ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, vals, percent)
    axes.flat[7].axis("off")
    fig.text(.5, .045, "Descriptive summary only: genotype, treatment, stimulus duration and time point are collapsed.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .07, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def end_summary_genotype(pdf, project, animal):
    d = animal[animal["Project"] == project].copy()
    if d.empty:
        return
    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project}: brief KI2TA-3 vs KI2TA-4 comparison (sex/treatment/time collapsed)",
                 fontsize=20, fontweight="bold", y=.985)
    for i, (col, label, percent) in enumerate(METRICS):
        ax = axes.flat[i]
        means, errors, vals = [], [], []
        for geno in ["KI2TA-3", "KI2TA-4"]:
            ad = d[d["Genotype"] == geno].groupby("Animal_ID", as_index=False)[col].mean()
            s = metric_values(ad[col], percent).dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            vals.extend(s.tolist())
        ax.bar([0, 1], means, yerr=errors, capsize=3, alpha=.55)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["KI2TA-3", "KI2TA-4"])
        ax.set_ylabel(label, fontsize=8); ax.set_title(label, fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=.20); ax.tick_params(labelsize=8)
        apply_smart_ylim(ax, vals, percent)
    axes.flat[7].axis("off")
    fig.text(.5, .045, "Descriptive summary only: sex, treatment, stimulus duration and time point are collapsed.",
             ha="center", fontsize=8.5)
    fig.tight_layout(rect=[.02, .07, .98, .95])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


# ============================================================================
# v1.8 PAPER-REFERENCE FIGURES
# These pages intentionally use the same group colors, treatment line styles,
# sex watermarks, and animal-level averaging as the core Atlas graph package.
# They are descriptive visualizations only; inferential statistics are not
# recalculated here.
# ============================================================================

def _animal_condition_mean(df, col, *, dur=None, tp=None, sex=None, geno=None, trt=None):
    """Return one mean value per animal after applying optional conditions."""
    if df is None or df.empty or col not in df.columns:
        return pd.DataFrame(columns=["Animal_ID", col])
    q = df.copy()
    if dur is not None and "Stimulus_Duration_s" in q.columns:
        q = q[np.isclose(pd.to_numeric(q["Stimulus_Duration_s"], errors="coerce"), float(dur), equal_nan=False)]
    if tp is not None and "Timepoint_Months" in q.columns:
        q = q[pd.to_numeric(q["Timepoint_Months"], errors="coerce").eq(float(tp))]
    if sex is not None and "Sex" in q.columns:
        q = q[q["Sex"].astype(str).eq(sex)]
    if geno is not None and "Genotype" in q.columns:
        q = q[q["Genotype"].astype(str).eq(geno)]
    if trt is not None and "Treatment" in q.columns:
        q = q[q["Treatment"].astype(str).eq(trt)]
    if q.empty:
        return pd.DataFrame(columns=["Animal_ID", col])
    q[col] = pd.to_numeric(q[col], errors="coerce")
    return q.groupby("Animal_ID", as_index=False)[col].mean().dropna(subset=[col])


def paper_timeline_page(pdf, project):
    """Simple manuscript-style experimental timeline for the longitudinal CPT story."""
    fig, ax = plt.subplots(figsize=(13.333, 7.5))
    ax.axis("off")
    fig.suptitle(f"{project}: longitudinal CPT experimental framework",
                 fontsize=22, fontweight="bold", y=.94)
    xs = np.array([0.20, 0.50, 0.80])
    y = .56
    ax.plot([xs[0], xs[-1]], [y, y], color="0.35", linewidth=2.4, transform=ax.transAxes)
    for x, tp in zip(xs, TPS):
        ax.scatter([x], [y], s=420, facecolor="white", edgecolor="0.25",
                   linewidth=2.0, transform=ax.transAxes, zorder=3)
        ax.text(x, y, f"{tp}\nmonths", transform=ax.transAxes,
                ha="center", va="center", fontsize=12, fontweight="bold")
        ax.text(x, y-.17, "Stage 4\nfixed 2.0 s baseline",
                transform=ax.transAxes, ha="center", va="top", fontsize=10)
        ax.annotate("", xy=(x, y-.02), xytext=(x, y-.12), xycoords=ax.transAxes,
                    arrowprops=dict(arrowstyle="->", lw=1.3, color="0.35"))
        ax.text(x, y-.29, "Probe 2b\nmixed 2.0 / 1.0 / 0.5 / 0.2 s",
                transform=ax.transAxes, ha="center", va="top", fontsize=10, fontweight="bold")
    ax.text(.5, .82,
            "Repeated attentional challenge across age/time point",
            transform=ax.transAxes, ha="center", fontsize=14)
    ax.text(.5, .11,
            "Paper-reference schematic only. Session inclusion/QC remains defined by Atlas and the extractor.",
            transform=ax.transAxes, ha="center", fontsize=9, color="0.35")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_sd_profile_metric(ax, project, tp, sex, animal, col, label, percent):
    d = animal[(animal["Project"] == project) &
               (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp) &
               (animal["Sex"] == sex)].copy()
    styles = group_style_map(project)
    vals = []
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty or col not in gd.columns:
            continue
        xs, ys, es = [], [], []
        for i, dur in enumerate(DURS):
            av = _animal_condition_mean(gd, col, dur=dur)
            s = metric_values(av[col], percent).dropna()
            if s.empty:
                continue
            xs.append(i); ys.append(float(s.mean())); es.append(sem(s))
        if not xs:
            continue
        st = styles[(geno, trt)]
        ax.errorbar(xs, ys, yerr=es, marker="o", markersize=4.8, capsize=3,
                    color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                    label=f"{geno} | {trt}")
        vals.extend((np.asarray(ys) - np.asarray(es)).tolist())
        vals.extend((np.asarray(ys) + np.asarray(es)).tolist())
    ax.set_xticks(range(4)); ax.set_xticklabels(["2.0", "1.0", "0.5", "0.2"])
    ax.set_xlabel("Stimulus duration (s)", fontsize=9)
    ax.set_ylabel(label, fontsize=9)
    ax.set_title(f"{sex}: {label}", fontsize=10.5, fontweight="bold")
    ax.grid(alpha=.20)
    ax.tick_params(labelsize=8.5)
    add_sex_watermark(ax, sex)
    apply_smart_ylim(ax, vals, percent)


def paper_sd_profile_page(pdf, project, tp, animal, page_kind):
    specs = {
        "rates": [
            ("Hit_Rate", "Hit rate (%)", True),
            ("False_Alarm_Rate", "False alarm rate (%)", True),
        ],
        "signal": [
            ("d_prime", "d′", False),
            ("criterion_c", "Response bias (c)", False),
        ],
        "latencies": [
            ("Mean_Session_Correct_Touch_Latency_s", "Correct touch latency (s)", False),
            ("Mean_Session_Reward_Retrieval_Latency_s", "Reward retrieval latency (s)", False),
        ],
    }
    metrics = specs[page_kind]
    fig, axes = plt.subplots(2, 2, figsize=(13.333, 8.0))
    fig.suptitle(f"{project} - {tp} months: Probe 2b stimulus-duration profile",
                 fontsize=19, fontweight="bold", y=.985)
    for r, (col, label, pct) in enumerate(metrics):
        for c, sex in enumerate(SEXES):
            _plot_sd_profile_metric(axes[r, c], project, tp, sex, animal, col, label, pct)
        sync_y_limits([axes[r, 0], axes[r, 1]])
    count_df = animal[(animal["Project"] == project) &
                      (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp)]
    combined_group_legend(fig, project, count_df, y=.035, fontsize=8.2)
    fig.text(.5, .008, "Mean +/- SEM across animals. Solid = treated; dotted = control. Female and male Y-axes are synchronized.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=[.03, .13, .98, .95], h_pad=2.4, w_pad=2.2)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _plot_longitudinal_dprime(ax, project, sex, dur, animal, show_individual=False):
    d = animal[(animal["Project"] == project) & (animal["Sex"] == sex)].copy()
    styles = group_style_map(project)
    vals = []
    for geno, trt in GROUP_ORDER[project]:
        gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
        if gd.empty or "d_prime" not in gd.columns:
            continue
        pivot_rows = []
        for tp in TPS:
            av = _animal_condition_mean(gd, "d_prime", dur=dur, tp=tp)
            if not av.empty:
                av["Timepoint_Months"] = tp
                pivot_rows.append(av)
        if not pivot_rows:
            continue
        long = pd.concat(pivot_rows, ignore_index=True)
        st = styles[(geno, trt)]
        if show_individual:
            pvt = long.pivot_table(index="Animal_ID", columns="Timepoint_Months", values="d_prime", aggfunc="mean")
            for _, row in pvt.iterrows():
                ys = [row.get(tp, np.nan) for tp in TPS]
                ax.plot(range(3), ys, color=st["color"], alpha=.17, linewidth=.8, zorder=1)
        means, errors = [], []
        for tp in TPS:
            s = pd.to_numeric(long.loc[long["Timepoint_Months"] == tp, "d_prime"], errors="coerce").dropna()
            means.append(float(s.mean()) if not s.empty else np.nan)
            errors.append(sem(s))
            vals.extend(s.tolist())
        ax.errorbar(range(3), means, yerr=errors, marker="o", markersize=5, capsize=3,
                    color=st["color"], linestyle=st["linestyle"], linewidth=st["linewidth"],
                    label=f"{geno} | {trt}", zorder=3)
    ax.set_xticks(range(3)); ax.set_xticklabels(["6", "9", "12"])
    ax.set_xlabel("Age / time point (months)", fontsize=9)
    ax.set_ylabel("d′", fontsize=9)
    ax.set_title(f"{sex} - {dur:g} s", fontsize=10.5, fontweight="bold")
    ax.grid(alpha=.20); ax.tick_params(labelsize=8.5)
    add_sex_watermark(ax, sex)
    apply_smart_ylim(ax, vals, False)


def paper_longitudinal_dprime_pages(pdf, project, animal, show_individual=False):
    for pair in [(2.0, 1.0), (0.5, 0.2)]:
        fig, axes = plt.subplots(2, 2, figsize=(13.333, 8.0))
        title = "Individual-mouse longitudinal d′" if show_individual else "Longitudinal d′ by stimulus duration"
        fig.suptitle(f"{project}: {title}", fontsize=19, fontweight="bold", y=.985)
        for r, dur in enumerate(pair):
            for c, sex in enumerate(SEXES):
                _plot_longitudinal_dprime(axes[r, c], project, sex, dur, animal, show_individual=show_individual)
            sync_y_limits([axes[r, 0], axes[r, 1]])
        count_df = animal[animal["Project"] == project]
        combined_group_legend(fig, project, count_df, y=.035, fontsize=8.2)
        footer = "Thin lines = individual mice; bold lines = group mean +/- SEM." if show_individual else "Group mean +/- SEM; female and male Y-axes are synchronized within stimulus duration."
        fig.text(.5, .008, footer, ha="center", fontsize=8)
        fig.tight_layout(rect=[.03, .13, .98, .95], h_pad=2.4, w_pad=2.2)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def _baseline_probe_delta(stage4, probe, col, project, tp, sex, geno, trt, percent):
    s4 = _animal_condition_mean(stage4[(stage4["Project"] == project)], col,
                                tp=tp, sex=sex, geno=geno, trt=trt)
    p2 = _animal_condition_mean(probe[(probe["Project"] == project)], col,
                                dur=2.0, tp=tp, sex=sex, geno=geno, trt=trt)
    if s4.empty or p2.empty:
        return pd.DataFrame(columns=["Animal_ID", "Delta"])
    m = s4.merge(p2, on="Animal_ID", suffixes=("_Stage4", "_Probe"))
    if m.empty:
        return pd.DataFrame(columns=["Animal_ID", "Delta"])
    a = metric_values(m[col + "_Stage4"], percent)
    b = metric_values(m[col + "_Probe"], percent)
    m["Delta"] = b - a
    return m[["Animal_ID", "Delta"]].dropna()


def _baseline_delta_values(stage4, probe, col, project, tp, percent):
    """Collect paired Stage-4 -> Probe deltas for all sex/group cells on one metric."""
    out = {}
    for sex in SEXES:
        for geno, trt in GROUP_ORDER[project]:
            dlt = _baseline_probe_delta(stage4, probe, col, project, tp, sex, geno, trt, percent)
            s = pd.to_numeric(dlt.get("Delta", pd.Series(dtype=float)), errors="coerce").dropna()
            out[(sex, geno, trt)] = s
    return out


def _apply_baseline_delta_ylim(ax, vals, metric_col):
    """Metric-aware zero-centred limits so small d′/c/latency changes remain visible."""
    s = pd.to_numeric(pd.Series(vals), errors="coerce").dropna()
    if s.empty:
        return
    # Robustly ignore a single extreme point when choosing the display range, but
    # never crop the actual data: the final limit includes the observed maximum.
    robust = float(np.nanpercentile(np.abs(s), 98)) if len(s) > 2 else float(np.nanmax(np.abs(s)))
    observed = float(np.nanmax(np.abs(s)))
    floors = {
        "Hit_Rate": 5.0,                         # percentage points
        "False_Alarm_Rate": 5.0,                # percentage points
        "d_prime": 0.25,                        # d′ units
        "criterion_c": 0.20,                    # criterion units
        "Mean_Session_Correct_Touch_Latency_s": 0.10,
        "Mean_Session_Reward_Retrieval_Latency_s": 0.10,
    }
    limit = max(floors.get(metric_col, 0.10), robust * 1.25, observed * 1.08)
    ax.set_ylim(-limit, limit)


def paper_baseline_change_page(pdf, project, tp, stage4, probe, page_kind):
    specs = {
        "rates": [("Hit_Rate", "Change in hit rate (percentage points)", True),
                  ("False_Alarm_Rate", "Change in false alarm rate (percentage points)", True)],
        "signal": [("d_prime", "Change in d′", False),
                   ("criterion_c", "Change in response bias (c)", False)],
        "latencies": [("Mean_Session_Correct_Touch_Latency_s", "Change in correct touch latency (s)", False),
                      ("Mean_Session_Reward_Retrieval_Latency_s", "Change in reward retrieval latency (s)", False)],
    }
    if stage4 is None or stage4.empty:
        return False

    # Pre-compute paired values. If there are no paired mice for an entire page,
    # do not generate a blank PDF page (the old latency pages could be empty).
    metric_cache = {}
    page_has_data = False
    for col, label, pct in specs[page_kind]:
        cache = _baseline_delta_values(stage4, probe, col, project, tp, pct)
        metric_cache[col] = cache
        if any(len(v) for v in cache.values()):
            page_has_data = True
    if not page_has_data:
        return False

    fig, axes = plt.subplots(2, 2, figsize=(13.333, 8.0))
    fig.suptitle(f"{project} - {tp} months: within-mouse Stage 4 to Probe 2b (2.0 s) change",
                 fontsize=18, fontweight="bold", y=.985)
    colors = group_color_map(project)

    for r, (col, label, pct) in enumerate(specs[page_kind]):
        row_axes = []
        row_all = []
        metric_has_data = any(len(v) for v in metric_cache[col].values())
        if not metric_has_data:
            for c in range(2):
                axes[r, c].axis("off")
            continue

        for c, sex in enumerate(SEXES):
            ax = axes[r, c]
            row_axes.append(ax)
            vals = []
            centers = np.arange(4, dtype=float)
            for gi, (geno, trt) in enumerate(GROUP_ORDER[project]):
                s = metric_cache[col][(sex, geno, trt)]
                if s.empty:
                    continue
                mean = float(s.mean()); err = sem(s)
                ax.bar([centers[gi]], [mean], width=.56, color=colors[(geno, trt)], alpha=.58,
                       edgecolor="0.35", linewidth=.65, zorder=2)
                ax.errorbar([centers[gi]], [mean], yerr=[err], fmt="none", ecolor="0.20",
                            capsize=3, elinewidth=1.0, zorder=6)
                jitter = np.linspace(-.08, .08, len(s)) if len(s) > 1 else np.array([0.0])
                ax.scatter(np.full(len(s), centers[gi]) + jitter, s, s=18,
                           color=colors[(geno, trt)], edgecolors="white", linewidths=.35, zorder=4)
                vals.extend(s.tolist())
                row_all.extend(s.tolist())
            if not vals:
                ax.axis("off")
                continue
            ax.axhline(0, color="0.25", linewidth=1.0, alpha=.7)
            ax.set_xticks(centers)
            ax.set_xticklabels([f"{g}\n{t}" for g, t in GROUP_ORDER[project]], fontsize=6.7)
            ax.set_ylabel(label, fontsize=8.5)
            ax.set_title(f"{sex}: {label}", fontsize=10, fontweight="bold")
            ax.grid(axis="y", alpha=.18); ax.tick_params(labelsize=8)
            add_sex_watermark(ax, sex)

        # Use one sensible metric-specific scale for Female and Male so they remain comparable.
        live = [ax for ax in row_axes if ax.has_data()]
        if live and row_all:
            for ax in live:
                _apply_baseline_delta_ylim(ax, row_all, col)

    fig.text(.5, .035,
             "Each dot = one mouse with paired Stage 4 and Probe 2b 2.0-s data. Delta = Probe 2b minus Stage 4; zero = no change.",
             ha="center", fontsize=8.2)
    fig.tight_layout(rect=[.03, .08, .98, .95], h_pad=2.5, w_pad=2.2)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    return True

def paper_dprime_heatmap_page(pdf, project, animal):
    """Publication-style treated-minus-control d′ overview across age and SD."""
    control, treated = project_controls(project)
    fig = plt.figure(figsize=(13.333, 6.5))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, .045], wspace=.22)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
    cax = fig.add_subplot(gs[0, 2])
    fig.suptitle(f"{project}: treatment effect on d′ across age and stimulus duration",
                 fontsize=19, fontweight="bold", y=.975)

    matrices = []
    for sex in SEXES:
        mat = np.full((2, len(TPS) * len(DURS)), np.nan)
        for ri, geno in enumerate(["KI2TA-3", "KI2TA-4"]):
            ci = 0
            for tp in TPS:
                for dur in DURS:
                    c = _animal_condition_mean(animal[(animal["Project"] == project)], "d_prime",
                                               dur=dur, tp=tp, sex=sex, geno=geno, trt=control)
                    t = _animal_condition_mean(animal[(animal["Project"] == project)], "d_prime",
                                               dur=dur, tp=tp, sex=sex, geno=geno, trt=treated)
                    if not c.empty and not t.empty:
                        mat[ri, ci] = (pd.to_numeric(t["d_prime"], errors="coerce").mean()
                                       - pd.to_numeric(c["d_prime"], errors="coerce").mean())
                    ci += 1
        matrices.append(mat)

    finite_parts = [m[np.isfinite(m)] for m in matrices if np.isfinite(m).any()]
    finite = np.concatenate(finite_parts) if finite_parts else np.array([-.1, .1])
    lim = max(float(np.nanmax(np.abs(finite))), .10)
    im = None
    repeated_sd = [f"{d:g}" for _tp in TPS for d in DURS]

    for ax, sex, mat in zip(axes, SEXES, matrices):
        im = ax.imshow(mat, aspect="auto", cmap="coolwarm", vmin=-lim, vmax=lim)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["KI2TA-3", "KI2TA-4"], fontsize=9.5)
        ax.set_xticks(range(len(repeated_sd)))
        ax.set_xticklabels(repeated_sd, fontsize=8)
        ax.set_xlabel("Stimulus duration (s)", fontsize=9, labelpad=8)
        # Separate sex and age headers so they never collide.
        ax.text(.5, 1.17, sex, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=12.5, fontweight="bold", clip_on=False)

        # Age headers centred over each four-SD block.
        block_centres = [(i * len(DURS) + (len(DURS) - 1) / 2) / (len(TPS) * len(DURS) - 1)
                         for i in range(len(TPS))]
        for xfrac, tp in zip(block_centres, TPS):
            ax.text(xfrac, 1.08, f"{tp} months", transform=ax.transAxes,
                    ha="center", va="bottom", fontsize=10, fontweight="bold", clip_on=False)
        for boundary in [3.5, 7.5]:
            ax.axvline(boundary, color="white", linewidth=3.0)

        # Cell labels stay readable without the redundant sex watermark.
        for r in range(mat.shape[0]):
            for c in range(mat.shape[1]):
                if np.isfinite(mat[r, c]):
                    ax.text(c, r, f"{mat[r,c]:+.2f}", ha="center", va="center",
                            fontsize=7.2, color="black", fontweight="semibold")
        ax.tick_params(axis="both", length=0)

    cbar = fig.colorbar(im, cax=cax)
    cbar.set_label(f"d′ difference ({treated} − {control})", fontsize=9.5, labelpad=10)
    fig.text(.5, .035,
             f"Descriptive mean difference only: red = higher d′ in {treated}; blue = higher d′ in {control}. No significance is implied.",
             ha="center", fontsize=8.4)
    fig.subplots_adjust(left=.07, right=.94, bottom=.17, top=.78)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)

def _paper_next_trial_metric_page(pdf, project, tp, next_animal, mode, metrics, title):
    """Two metrics x two sexes = four panels; suppress page if none of the metrics have data."""
    d = next_animal[(next_animal["Project"] == project) &
                    (pd.to_numeric(next_animal["Timepoint_Months"], errors="coerce") == tp)].copy()
    if d.empty:
        return False
    fig, axes = plt.subplots(len(metrics), 2, figsize=(13.333, 8.0), squeeze=False)
    any_data = False
    for r, (col, label, pct) in enumerate(metrics):
        row_axes = []
        for c, sex in enumerate(SEXES):
            ax = axes[r, c]
            before = len(ax.lines) + len(ax.collections) + len(ax.patches)
            if mode == "outcome":
                _plot_next_trial_outcome_metric(ax, project, tp, sex, next_animal, col, label, pct)
            else:
                _plot_trial_carryover_metric(ax, project, tp, sex, next_animal, col, label, pct)
            after = len(ax.lines) + len(ax.collections) + len(ax.patches)
            if after > before and ax.axison:
                any_data = True
            row_axes.append(ax)
        sync_y_limits(row_axes)
    if not any_data:
        plt.close(fig)
        return False
    fig.suptitle(f"{project} - {tp} months: {title}", fontsize=18, fontweight="bold", y=.985)
    combined_group_legend(fig, project, d, y=.04, fontsize=8.2)
    if mode == "outcome":
        footer = "Previous-outcome comparison; stimulus durations are collapsed. Dots are mouse-level means."
    else:
        footer = "Previous-difficulty comparison: easy = 1.0/2.0 s; hard = 0.2/0.5 s. Dots are mouse-level means."
    fig.text(.5, .01, footer, ha="center", fontsize=8.1)
    fig.tight_layout(rect=[.03, .13, .98, .95], h_pad=2.3, w_pad=2.2)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    return True


def paper_next_trial_pages(pdf, project, tp, next_animal):
    """Curated next-trial section: rates together, then the two most useful latencies."""
    rate_metrics = [
        ("Hit_Rate", "Next-trial hit rate (%)", True),
        ("False_Alarm_Rate", "Next-trial false alarm rate (%)", True),
    ]
    latency_metrics = [
        ("Mean_Session_Correct_Touch_Latency_s", "Next correct latency (s)", False),
        ("Mean_Session_Reward_Retrieval_Latency_s", "Next reward latency (s)", False),
    ]
    _paper_next_trial_metric_page(pdf, project, tp, next_animal, "outcome", rate_metrics,
                                  "next-trial behavior after previous outcome - rates")
    _paper_next_trial_metric_page(pdf, project, tp, next_animal, "outcome", latency_metrics,
                                  "next-trial behavior after previous outcome - latencies")
    _paper_next_trial_metric_page(pdf, project, tp, next_animal, "difficulty", rate_metrics,
                                  "next-trial behavior after easy vs hard previous trial - rates")
    _paper_next_trial_metric_page(pdf, project, tp, next_animal, "difficulty", latency_metrics,
                                  "next-trial behavior after easy vs hard previous trial - latencies")


def paper_reference_title_page(pdf, project):
    fig = plt.figure(figsize=(13.333, 7.5))
    fig.text(.5, .70, f"{project} CPT", ha="center", fontsize=30, fontweight="bold")
    fig.text(.5, .56, "Paper Reference Figures", ha="center", fontsize=28, fontweight="bold")
    fig.text(.5, .40,
             "Literature-comparable stimulus-duration curves + longitudinal views +\n"
             "within-mouse baseline change + individual trajectories + vigilance + curated trial-history effects",
             ha="center", fontsize=13, linespacing=1.45)
    fig.text(.5, .16,
             "These pages are descriptive graph outputs. Atlas QC/eligibility and any inferential statistics remain unchanged.",
             ha="center", fontsize=9.5, color="0.35")
    fig.text(.5, .07, f"ATLAS CPT Graph Maker v{VERSION}", ha="center", fontsize=9)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def make_paper_reference_pdf(path, project, animal, stage4_animal, decile_animal, next_trial, feedback_animal=None, transition_animal=None):
    """Create the v1.8 manuscript/reference-oriented figure package."""
    with PdfPages(path) as pdf:
        paper_reference_title_page(pdf, project)
        paper_timeline_page(pdf, project)

        # Conventional CPT/iCPT stimulus-duration profiles, capped at four panels/page.
        for tp in TPS:
            if not ((animal["Project"] == project) &
                    (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp)).any():
                continue
            for kind in ["rates", "signal", "latencies"]:
                paper_sd_profile_page(pdf, project, tp, animal, kind)

        # Longitudinal group summaries followed by individual-mouse spaghetti views.
        paper_longitudinal_dprime_pages(pdf, project, animal, show_individual=False)
        paper_longitudinal_dprime_pages(pdf, project, animal, show_individual=True)

        # Within-mouse Stage 4 -> Probe 2b change, if baseline input is available.
        if stage4_animal is not None and not stage4_animal.empty:
            for tp in TPS:
                if ((animal["Project"] == project) &
                    (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp)).any():
                    for kind in ["rates", "signal", "latencies"]:
                        paper_baseline_change_page(pdf, project, tp, stage4_animal, animal, kind)

        # Compact overview of the d-prime treatment-control pattern.
        paper_dprime_heatmap_page(pdf, project, animal)

        # Existing v1.7 vigilance and trial-history analyses are re-used here so the
        # manuscript package contains the standard figures and the more novel analyses.
        if decile_animal is not None and not decile_animal.empty:
            for tp in TPS:
                if ((animal["Project"] == project) &
                    (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp)).any():
                    for kind in ["rates", "signal", "latencies"]:
                        within_session_decile_comparison_pages(pdf, project, tp, decile_animal, kind)
        if next_trial is not None and not next_trial.empty:
            for tp in TPS:
                if ((animal["Project"] == project) &
                    (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp)).any():
                    paper_next_trial_pages(pdf, project, tp, next_trial)
        if feedback_animal is not None and not feedback_animal.empty:
            for tp in TPS:
                if ((animal["Project"] == project) &
                    (pd.to_numeric(animal["Timepoint_Months"], errors="coerce") == tp)).any():
                    feedback_explainer_page(pdf, project, tp)
                    feedback_detail_combined_pages(pdf, project, tp, feedback_animal)
                    if transition_animal is not None and not transition_animal.empty:
                        response_stay_combined_page(pdf, project, tp, transition_animal)

def write_plot_values(animal, outdir):
    rows = []
    for col, label, percent in METRICS:
        if col not in animal.columns:
            continue
        q = animal[["Project", "Animal_ID", "Cohort", "Sex", "Genotype", "Treatment",
                    "Timepoint_Months", "Stimulus_Duration_s", col]].copy()
        q["Metric"] = label
        q["Value"] = metric_values(q[col], percent)
        q = q.drop(columns=[col])
        rows.append(q)
    if rows:
        pd.concat(rows, ignore_index=True).to_csv(outdir / "GRAPH_PLOTTED_ANIMAL_VALUES.csv", index=False)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input_path", nargs="?")
    ap.add_argument("-o", "--output-folder")
    ap.add_argument("--preview", action="store_true",
                    help="Make a small preview PDF instead of the full graph package.")
    ap.add_argument("--project", choices=["Lecanemab", "Vaccine", "Both"], default="Both",
                    help="Project to graph in preview/full mode.")
    ap.add_argument("--timepoint", choices=["6", "9", "12", "All"], default="All",
                    help="Time point to graph in preview/full mode.")
    args = ap.parse_args()

    inp = args.input_path or choose_file(
        "Select 67-column Probe 2b extractor CSV, or cancel to choose old analysis folder",
        [("CSV files", "*.csv"), ("All files", "*.*")]
    )
    if not inp:
        inp = choose_folder("Select ATLAS_ANALYSIS_OUTPUT folder (old workflow)")
    if not inp:
        inp = input("Paste 67-column extractor CSV path or Atlas analysis output folder path: ").strip().strip('"')
    out = args.output_folder or choose_folder("Select graph output folder")
    if not out:
        out = input("Paste graph output folder path: ").strip().strip('"')

    root = Path(inp)
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)

    names = {
        "animal": "ANALYSIS_PROBE2B_ANIMAL_CONDITION.csv",
        "session": "ANALYSIS_PROBE2B_SESSION_METRICS.csv",
        "trial": "ANALYSIS_PROBE2B_TRIAL_QC.csv",
        "next": "ANALYSIS_NEXT_TRIAL.csv",
        "stage4_animal": "ANALYSIS_STAGE4_ANIMAL_CONDITION.csv",
        "contrasts": "ANALYSIS_PLANNED_TREATMENT_CONTRASTS.csv",
    }
    paths = {}
    if root.is_file() and root.suffix.lower() == ".csv":
        sidecar_dir = root.parent
        raw = pd.read_csv(root)
        animal = normalize_extractor_67(raw)
        session = animal.copy()
        trial_path = find_sidecar_csv(sidecar_dir, ["PROBE2B_TRIAL_MASTER*.csv"])
        decile_path = find_sidecar_csv(sidecar_dir, ["PROBE2B_WITHIN_SESSION_DECILES*.csv"])
        next_path = find_sidecar_csv(sidecar_dir, ["PROBE2B_NEXT_TRIAL*.csv", "ANALYSIS_NEXT_TRIAL*.csv"])
        stage4_path = find_sidecar_csv(sidecar_dir, [
            "STAGE4_BASELINE_TIMEPOINT_AVERAGES*.csv",
            "STAGE4_BASELINE_SESSION_METRICS*.csv",
            "BASELINE_TO_PROBE_2S_LONG*.csv",
            "ANALYSIS_STAGE4_ANIMAL_CONDITION*.csv",
        ])
        paths = {
            "animal": root,
            "session": root,
            "trial": trial_path,
            "next": next_path,
            "stage4_animal": stage4_path,
            "contrasts": None,
        }
        trial = clean_meta(pd.read_csv(trial_path)) if trial_path else pd.DataFrame()
        if next_path:
            next_trial = make_next_trial_animal(normalize_next_trial_csv(pd.read_csv(next_path)))
        else:
            next_trial = pd.DataFrame()
        if stage4_path:
            stage4_animal = normalize_extractor_67(pd.read_csv(stage4_path))
            if "Stimulus_Duration_s" not in stage4_animal.columns:
                stage4_animal["Stimulus_Duration_s"] = 2.0
        else:
            stage4_animal = pd.DataFrame()
        contrasts = pd.DataFrame()
        authoritative, metadata_path = load_authoritative_metadata(root.parent)
    else:
        paths = {k: find_file(root, v) for k, v in names.items()}
        if paths["animal"] is None:
            raise FileNotFoundError(
                "Neither a 67-column extractor CSV nor ANALYSIS_PROBE2B_ANIMAL_CONDITION.csv was found."
            )

        data = {k: clean_meta(safe_read(v)) for k, v in paths.items()}
        authoritative, metadata_path = load_authoritative_metadata(root)
        animal = data["animal"]
        session = data["session"]
        trial = data["trial"]
        next_trial = make_next_trial_animal(data["next"])
        stage4_animal = data["stage4_animal"]
        contrasts = data["contrasts"]

    # Keep every graph input aligned to the same corrected animal metadata.
    # Planned contrasts remain analysis outputs and are intentionally not
    # recomputed or altered by the graph maker.
    if not authoritative.empty:
        animal = apply_authoritative_metadata(animal, authoritative)
        session = apply_authoritative_metadata(session, authoritative)
        trial = apply_authoritative_metadata(trial, authoritative)
        next_trial = apply_authoritative_metadata(next_trial, authoritative)
        stage4_animal = apply_authoritative_metadata(stage4_animal, authoritative)

    # Next-trial / response-history graphing is intentionally disabled in this version.
    feedback_animal = pd.DataFrame()
    transition_animal = pd.DataFrame()

    write_plot_values(animal, outdir)
    bins = compute_trial_bins(trial) if not trial.empty else pd.DataFrame()
    correction_animal = make_correction_trial_animal(trial) if not trial.empty else pd.DataFrame()
    if not correction_animal.empty and not authoritative.empty:
        correction_animal = apply_authoritative_metadata(correction_animal, authoritative)
    if not correction_animal.empty:
        correction_animal.to_csv(outdir / "CORRECTION_TRIAL_ANIMAL_METRICS.csv", index=False)

    decile_animal = make_decile_animal_metrics(trial) if not trial.empty else pd.DataFrame()
    if not decile_animal.empty and not authoritative.empty:
        decile_animal = apply_authoritative_metadata(decile_animal, authoritative)
    if not decile_animal.empty:
        decile_animal.to_csv(outdir / "WITHIN_SESSION_DECILE_ANIMAL_METRICS.csv", index=False)

    iti_decile_animal = make_iti_decile_animal_metrics(trial) if not trial.empty else pd.DataFrame()
    if not iti_decile_animal.empty and not authoritative.empty:
        iti_decile_animal = apply_authoritative_metadata(iti_decile_animal, authoritative)
    if not iti_decile_animal.empty:
        iti_decile_animal.to_csv(outdir / "ITI_WITHIN_SESSION_DECILE_ANIMAL_METRICS.csv", index=False)

    iti_animal = make_iti_animal_metrics(trial) if not trial.empty else pd.DataFrame()
    if not iti_animal.empty and not authoritative.empty:
        iti_animal = apply_authoritative_metadata(iti_animal, authoritative)
    if not iti_animal.empty:
        iti_animal.to_csv(outdir / "ITI_ANIMAL_METRICS.csv", index=False)
        print(f"ITI analysis: {len(iti_animal):,} animal-condition rows")
    else:
        print("ITI analysis: not available (PROBE2B_TRIAL_MASTER missing Current_ITI_s or required CPT columns).")
    iti_summary = iti_whole_session(iti_animal) if not iti_animal.empty else pd.DataFrame()

    projects_to_run = ["Lecanemab", "Vaccine"] if args.project == "Both" else [args.project]
    tps_to_run = TPS if args.timepoint == "All" else [int(args.timepoint)]
    if args.preview:
        projects_to_run = projects_to_run[:1]
        tps_to_run = tps_to_run[:1]

    produced = []
    for project in projects_to_run:
        if not (animal["Project"] == project).any():
            continue
        project_dir = outdir / project
        project_dir.mkdir(parents=True, exist_ok=True)

        for tp in tps_to_run:
            if not ((animal["Project"] == project) & (animal["Timepoint_Months"] == tp)).any():
                continue
            suffix = "_PREVIEW" if args.preview else ""

            # 1) Whole-session averaged mixed-SD Probe 2b general measures + latencies only.
            # Stage 4 baseline comparisons are intentionally omitted.
            general_path = project_dir / f"{project}_{tp}_months_Probe2b_Whole_Session_ATLAS_CPT_v1_8{suffix}.pdf"
            with PdfPages(general_path) as pdf:
                divider_page(pdf, project, tp)
                whole_session_sex_comparison_pages(pdf, project, tp, animal, contrasts)
            produced.append(str(general_path.relative_to(outdir)))

            # 2) Vigilance only
            if not decile_animal.empty:
                vigilance_path = project_dir / f"{project}_{tp}_months_Vigilance_ATLAS_CPT_v1_8{suffix}.pdf"
                with PdfPages(vigilance_path) as pdf:
                    divider_page(pdf, project, tp)
                    page_kinds = ["rates"] if args.preview else ["rates", "signal", "latencies"]
                    for page_kind in page_kinds:
                        within_session_decile_comparison_pages(pdf, project, tp, decile_animal, page_kind)
                produced.append(str(vigilance_path.relative_to(outdir)))

            # 3) Combined ITI pages: 2s and 3s shown as separate panels instead of overlaid lines.
            if not iti_summary.empty:
                iti_whole_path = project_dir / f"{project}_{tp}_months_ITI_Whole_Session_2s_vs_3s_ATLAS_CPT_v1_8{suffix}.pdf"
                with PdfPages(iti_whole_path) as pdf:
                    divider_page(pdf, project, tp)
                    iti_metric_page(pdf, project, tp, iti_summary, "rates")
                    iti_metric_page(pdf, project, tp, iti_summary, "signal")
                    if not args.preview:
                        iti_metric_page(pdf, project, tp, iti_summary, "latencies")
                produced.append(str(iti_whole_path.relative_to(outdir)))

            if not iti_decile_animal.empty:
                iti_avg_path = project_dir / f"{project}_{tp}_months_ITI_Vigilance_D1-D10_Average_2s_vs_3s_ATLAS_CPT_v1_8{suffix}.pdf"
                with PdfPages(iti_avg_path) as pdf:
                    divider_page(pdf, project, tp)
                    page_kinds = ["rates"] if args.preview else ["rates", "signal", "latencies"]
                    for page_kind in page_kinds:
                        iti_vigilance_average_page(pdf, project, tp, iti_decile_animal, page_kind)
                produced.append(str(iti_avg_path.relative_to(outdir)))

            # 4) Compatibility outputs: whole-session and vigilance pages split into separate 2s and 3s ITI PDFs.
            for iti in [2, 3]:
                if not iti_summary.empty:
                    iti_data = iti_summary[np.isclose(pd.to_numeric(iti_summary["Current_ITI_s"], errors="coerce"), iti)].copy()
                    if not iti_data.empty:
                        split_path = project_dir / f"{project}_{tp}_months_Probe2b_Whole_Session_{iti}s_ITI_ATLAS_CPT_v1_8{suffix}.pdf"
                        with PdfPages(split_path) as pdf:
                            divider_page(pdf, project, tp)
                            whole_session_sex_comparison_pages(pdf, project, tp, iti_data, contrasts, title_suffix=f"{iti}s ITI")
                        produced.append(str(split_path.relative_to(outdir)))
                if not iti_decile_animal.empty:
                    iti_dec = iti_decile_animal[np.isclose(pd.to_numeric(iti_decile_animal["Current_ITI_s"], errors="coerce"), iti)].copy()
                    if not iti_dec.empty:
                        vig_path = project_dir / f"{project}_{tp}_months_Vigilance_{iti}s_ITI_ATLAS_CPT_v1_8{suffix}.pdf"
                        with PdfPages(vig_path) as pdf:
                            divider_page(pdf, project, tp)
                            page_kinds = ["rates"] if args.preview else ["rates", "signal", "latencies"]
                            for page_kind in page_kinds:
                                within_session_decile_comparison_pages(pdf, project, tp, iti_dec, page_kind)
                        produced.append(str(vig_path.relative_to(outdir)))

            # 5) ITI delta only: 3s ITI minus 2s ITI within each mixed-SD Probe 2b stimulus duration.
            if not iti_summary.empty:
                iti_path = project_dir / f"{project}_{tp}_months_ITI_Delta_3s_minus_2s_ATLAS_CPT_v1_8{suffix}.pdf"
                with PdfPages(iti_path) as pdf:
                    divider_page(pdf, project, tp)
                    iti_delta_page(pdf, project, tp, iti_summary, "signal")
                    iti_delta_page(pdf, project, tp, iti_summary, "rates")
                    iti_delta_page(pdf, project, tp, iti_summary, "latencies")
                produced.append(str(iti_path.relative_to(outdir)))

        if args.preview:
            continue

        comparison_path = project_dir / f"{project}_Timepoint_Comparison_ATLAS_CPT_v1_8.pdf"
        with PdfPages(comparison_path) as pdf:
            comparison_title_page(pdf, project, animal, authoritative)
            animal_ids_page(pdf, project, animal)
            for dur in DURS:
                for page_kind in ["rates", "signal", "latencies"]:
                    timepoint_duration_comparison_page(pdf, project, animal, dur, page_kind)
        produced.append(str(comparison_path.relative_to(outdir)))

        # Keep the treatment-minus-control d-prime heatmap as its own clean PDF.
        # Lecanemab project = Lecanemab - PBS; Vaccine project = Vaccine - Sham.
        heatmap_path = project_dir / f"{project}_Treatment_Minus_Control_dPrime_Heatmap_ATLAS_CPT_v1_8.pdf"
        with PdfPages(heatmap_path) as pdf:
            paper_dprime_heatmap_page(pdf, project, animal)
        produced.append(str(heatmap_path.relative_to(outdir)))

        # The former all-in-one Paper Reference PDF is intentionally not generated.
        # Next-trial and response-behavior PDFs are intentionally not generated.

    (outdir / "GRAPH_MAKER_RUN_LOG.txt").write_text(
        f"ATLAS CPT Graph Maker v{VERSION}\n\n"
        f"Input: {root}\n\n"
        "Main layout: Project folders -> separate Probe 2b Whole Session, Vigilance, and ITI Effect PDFs per time point.\n"
        "A general 6/9/12-month comparison PDF and a separate treatment-minus-control d-prime heatmap PDF are also produced per project.\n"
        "Stage 4 baseline comparisons are intentionally omitted.\n"
        "Incorrect-touch latency is intentionally omitted from the compact story pages.\n"
        "Descriptive sex and strain/genotype comparison pages are intentionally omitted.\n"
        "Timepoint comparison pages show 6, 9 and 12 months on the x-axis for each stimulus duration.\n"
        "Whole-session general PDFs use mixed-SD Probe 2b data only.\n"
        "Next-trial and response-history graph pages are intentionally disabled in this version.\n"
        "Correction-trial slides are derived directly from PROBE2B_TRIAL_MASTER when explicit correction fields are present.\n"
        "Correction-trial metrics are exported to CORRECTION_TRIAL_ANIMAL_METRICS.csv for audit/reuse.\n"
        "Correction trials are kept separate from standard CPT HR/FAR/d-prime/c calculations.\n"
        "Within-session 10-decile vigilance slides are derived directly from PROBE2B_TRIAL_MASTER and included for each sex/timepoint.\n"
        "Within-session decile metrics are exported to WITHIN_SESSION_DECILE_ANIMAL_METRICS.csv.\n"
        "Combined ITI Whole Session PDFs show female 2s, female 3s, male 2s and male 3s as separate panels.\n"
        "Combined D1-D10 ITI Vigilance Average PDFs show 2s vs 3s as labeled bar/dot comparisons with paired animal lines.\n"
        "ITI-split Whole Session and Vigilance PDFs are still generated separately for 2s and 3s ITI for compatibility.\n"
        "ITI Delta PDFs show 3s ITI minus 2s ITI as bar/dot plots within each Probe 2b stimulus duration, averaged across Probe sessions 1-4 within mouse.\n"
        "ITI metrics are exported to ITI_ANIMAL_METRICS.csv for audit/reuse.\n"
        "Treatment heatmap PDF shows descriptive d-prime mean difference: Lecanemab minus PBS or Vaccine minus Sham, split by sex, age, genotype, and stimulus duration.\n\n"
        f"Authoritative metadata: {metadata_path if metadata_path else 'NOT FOUND; fell back to analysis CSV'}\n\n"
        "Files used:\n" +
        "\n".join(f"{k}: {v if v else 'NOT FOUND'}" for k, v in paths.items()) +
        "\n\nOutputs:\n" + "\n".join(produced) +
        "\n\nThe graph maker does not alter Atlas eligibility, QC, or inferential statistics.\n",
        encoding="utf-8"
    )

    print("\nDONE")
    print("Output folder:", outdir)
    for name in produced:
        print(" -", name)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            Path("GRAPH_MAKER_ERROR_LOG.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        sys.exit(1)
