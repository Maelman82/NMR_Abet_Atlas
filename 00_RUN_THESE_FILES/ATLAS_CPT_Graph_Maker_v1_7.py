
from __future__ import annotations

import sys, traceback
import time
import math
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

VERSION = "1.13-progress"

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
    ("Mean_Session_Incorrect_Touch_Latency_s", "Incorrect touch latency (s)", False),
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
    pdf.savefig(fig, bbox_inches="tight")
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

    offsets = np.linspace(-.27, .27, max(1, len(group_present)))
    width = .16

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
    offsets = np.linspace(-.27, .27, max(1, len(group_present)))
    width = .16

    fig, axes = plt.subplots(2, 4, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: next-trial behavior after easy vs hard previous trial",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(metrics):
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            xpos = np.arange(len(cats), dtype=float) + offsets[gi]
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

        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(["Easy prev\n1.0/2.0 s" if "easy" in c else "Hard prev\n0.2/0.5 s" for c in cats],
                           fontsize=8)
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
    offsets = np.linspace(-.27, .27, max(1, len(group_present)))
    width = .16

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle(f"{project} - {tp} months - {sex}: next-trial behavior",
                 fontsize=20, fontweight="bold", y=.985)

    for i, (col, label, percent) in enumerate(metrics):
        ax = axes.flat[i]
        allvals = []
        for gi, (geno, trt) in enumerate(group_present):
            gd = d[(d["Genotype"] == geno) & (d["Treatment"] == trt)]
            xpos = np.arange(len(cats), dtype=float) + offsets[gi]
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

        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, rotation=10, ha="center", fontsize=8)
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
            ("d_prime", "d prime", False),
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
            ("d_prime", "d prime", False),
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
    offsets = np.linspace(-.27, .27, max(1, len(group_present)))
    width = .16

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


def progress(message):
    """Print an immediate timestamped progress message to the console."""
    now = time.strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


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
    progress(f"Input selected: {root}")
    progress(f"Output folder: {outdir}")
    outdir.mkdir(parents=True, exist_ok=True)
    progress("Output folder ready.")

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
        progress("[1/9] Loading 67-column Probe 2b CSV...")
        t0 = time.perf_counter()
        raw = pd.read_csv(root)
        progress(f"      Loaded {len(raw):,} rows in {time.perf_counter()-t0:.1f}s.")
        progress("[2/9] Normalizing graph-maker columns...")
        t0 = time.perf_counter()
        animal = normalize_extractor_67(raw)
        session = animal.copy()
        progress(f"      Normalized to {len(animal):,} graph rows in {time.perf_counter()-t0:.1f}s.")
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
        progress("[3/9] Loading sidecar files beside the 67-column CSV...")
        progress(f"      Trial master: {trial_path.name if trial_path else 'NOT FOUND'}")
        progress(f"      Next-trial: {next_path.name if next_path else 'NOT FOUND'}")
        progress(f"      Stage 4: {stage4_path.name if stage4_path else 'NOT FOUND'}")
        if trial_path:
            t0 = time.perf_counter()
            trial = clean_meta(pd.read_csv(trial_path))
            progress(f"      Trial master loaded: {len(trial):,} rows in {time.perf_counter()-t0:.1f}s.")
        else:
            trial = pd.DataFrame()
        if next_path:
            t0 = time.perf_counter()
            progress("      Processing next-trial file...")
            next_trial = make_next_trial_animal(normalize_next_trial_csv(pd.read_csv(next_path)))
            progress(f"      Next-trial metrics ready: {len(next_trial):,} rows in {time.perf_counter()-t0:.1f}s.")
        else:
            next_trial = pd.DataFrame()
        if stage4_path:
            t0 = time.perf_counter()
            progress("      Processing Stage 4 baseline file...")
            stage4_animal = normalize_extractor_67(pd.read_csv(stage4_path))
            if "Stimulus_Duration_s" not in stage4_animal.columns:
                stage4_animal["Stimulus_Duration_s"] = 2.0
            progress(f"      Stage 4 ready: {len(stage4_animal):,} rows in {time.perf_counter()-t0:.1f}s.")
        else:
            stage4_animal = pd.DataFrame()
        contrasts = pd.DataFrame()
        progress("[4/9] Loading authoritative animal metadata...")
        authoritative, metadata_path = load_authoritative_metadata(root.parent)
        progress(f"      Metadata: {metadata_path if metadata_path else 'NOT FOUND; using analysis CSV labels'}")
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
    progress("[5/9] Applying authoritative metadata to graph inputs...")
    if not authoritative.empty:
        animal = apply_authoritative_metadata(animal, authoritative)
        session = apply_authoritative_metadata(session, authoritative)
        trial = apply_authoritative_metadata(trial, authoritative)
        next_trial = apply_authoritative_metadata(next_trial, authoritative)
        stage4_animal = apply_authoritative_metadata(stage4_animal, authoritative)
    progress("      Metadata alignment complete.")

    progress("[6/9] Writing plotted-animal audit values...")
    write_plot_values(animal, outdir)
    progress("      GRAPH_PLOTTED_ANIMAL_VALUES.csv written.")

    progress("[7/9] Deriving trial-level summary metrics (this can be the slow step)...")
    t0 = time.perf_counter()
    bins = compute_trial_bins(trial) if not trial.empty else pd.DataFrame()
    progress(f"      First/last-half trial bins complete in {time.perf_counter()-t0:.1f}s ({len(bins):,} rows).")
    t0 = time.perf_counter()
    progress("      Calculating correction-trial metrics...")
    correction_animal = make_correction_trial_animal(trial) if not trial.empty else pd.DataFrame()
    if not correction_animal.empty and not authoritative.empty:
        correction_animal = apply_authoritative_metadata(correction_animal, authoritative)
    if not correction_animal.empty:
        correction_animal.to_csv(outdir / "CORRECTION_TRIAL_ANIMAL_METRICS.csv", index=False)
    progress(f"      Correction-trial metrics complete in {time.perf_counter()-t0:.1f}s ({len(correction_animal):,} rows).")

    t0 = time.perf_counter()
    progress("      Calculating within-session decile metrics...")
    decile_animal = make_decile_animal_metrics(trial) if not trial.empty else pd.DataFrame()
    if not decile_animal.empty and not authoritative.empty:
        decile_animal = apply_authoritative_metadata(decile_animal, authoritative)
    if not decile_animal.empty:
        decile_animal.to_csv(outdir / "WITHIN_SESSION_DECILE_ANIMAL_METRICS.csv", index=False)
    progress(f"      Within-session deciles complete in {time.perf_counter()-t0:.1f}s ({len(decile_animal):,} rows).")

    projects_to_run = ["Lecanemab", "Vaccine"] if args.project == "Both" else [args.project]
    tps_to_run = TPS if args.timepoint == "All" else [int(args.timepoint)]
    if args.preview:
        projects_to_run = projects_to_run[:1]
        tps_to_run = tps_to_run[:1]

    progress("[8/9] Building graph PDFs...")
    produced = []
    for project in projects_to_run:
        if not (animal["Project"] == project).any():
            continue
        project_dir = outdir / project
        project_dir.mkdir(parents=True, exist_ok=True)
        progress(f"      {project}: output folder ready.")

        for tp in tps_to_run:
            if not ((animal["Project"] == project) & (animal["Timepoint_Months"] == tp)).any():
                continue
            suffix = "_PREVIEW" if args.preview else ""
            pdf_path = project_dir / f"{project}_{tp}_months_ATLAS_CPT_v1_12{suffix}.pdf"
            progress(f"      Creating {project} {tp}-month PDF...")
            tpdf = time.perf_counter()
            with PdfPages(pdf_path) as pdf:
                timepoint_title_page(pdf, project, tp, animal, authoritative)
                if not stage4_animal.empty:
                    page_kinds = ["rates", "signal"] if args.preview else ["rates", "signal", "latencies"]
                    for page_kind in page_kinds:
                        stage4_probe_combined_page(pdf, project, tp, stage4_animal, animal, page_kind)
                if not next_trial.empty:
                    for sex in SEXES:
                        next_trial_page(pdf, project, tp, sex, next_trial)
                        trial_carryover_page(pdf, project, tp, sex, next_trial)
                        if args.preview:
                            break
                if not correction_animal.empty:
                    for sex in SEXES:
                        correction_trial_page(pdf, project, tp, sex, correction_animal)
                        if args.preview:
                            break
                if not decile_animal.empty:
                    for sex in SEXES:
                        page_kinds = ["rates"] if args.preview else ["rates", "signal", "latencies"]
                        for page_kind in page_kinds:
                            within_session_decile_story_page(pdf, project, tp, sex, decile_animal, page_kind)
                        if args.preview:
                            break

            produced.append(str(pdf_path.relative_to(outdir)))
            progress(f"      Finished {pdf_path.name} in {time.perf_counter()-tpdf:.1f}s.")

        if args.preview:
            continue

        comparison_path = project_dir / f"{project}_Timepoint_Comparison_ATLAS_CPT_v1_12.pdf"
        progress(f"      Creating {project} timepoint-comparison PDF...")
        tpdf = time.perf_counter()
        with PdfPages(comparison_path) as pdf:
            comparison_title_page(pdf, project, animal, authoritative)
            animal_ids_page(pdf, project, animal)
            for dur in DURS:
                for page_kind in ["rates", "signal", "latencies"]:
                    timepoint_duration_comparison_page(pdf, project, animal, dur, page_kind)
        produced.append(str(comparison_path.relative_to(outdir)))
        progress(f"      Finished {comparison_path.name} in {time.perf_counter()-tpdf:.1f}s.")

    progress("[9/9] Writing run log...")
    (outdir / "GRAPH_MAKER_RUN_LOG.txt").write_text(
        "ATLAS CPT Graph Maker v1.13-progress\n\n"
        f"Input: {root}\n\n"
        "Main layout: Project folders -> one compact PDF per time point -> one comparison PDF.\n"
        "Each timepoint PDF contains three combined-sex Stage 4 baseline -> Probe 2b slides.\n"
        "Stage 4 slides use female panels on the left and male panels on the right.\n"
        "Incorrect-touch latency is intentionally omitted from the compact story pages.\n"
        "Descriptive sex and strain/genotype comparison pages are intentionally omitted.\n"
        "Timepoint comparison pages show 6, 9 and 12 months on the x-axis for each stimulus duration.\n"
        "First data slide is Stage 4 baseline -> Probe 2b when Stage 4 data are available.\n"
        "Next-trial slides are included when PROBE2B_NEXT_TRIAL is found beside the selected 67-column CSV.\n"
        "Correction-trial slides are derived directly from PROBE2B_TRIAL_MASTER when explicit correction fields are present.\n"
        "Correction-trial metrics are exported to CORRECTION_TRIAL_ANIMAL_METRICS.csv for audit/reuse.\n"
        "Correction trials are kept separate from standard CPT HR/FAR/d-prime/c calculations.\n"
        "Within-session 10-decile vigilance slides are derived directly from PROBE2B_TRIAL_MASTER and included for each sex/timepoint.\n"
        "Within-session decile metrics are exported to WITHIN_SESSION_DECILE_ANIMAL_METRICS.csv.\n"
        "Early-vs-late session-number slides remain omitted from this compact version.\n\n"
        f"Authoritative metadata: {metadata_path if metadata_path else 'NOT FOUND; fell back to analysis CSV'}\n\n"
        "Files used:\n" +
        "\n".join(f"{k}: {v if v else 'NOT FOUND'}" for k, v in paths.items()) +
        "\n\nOutputs:\n" + "\n".join(produced) +
        "\n\nThe graph maker does not alter Atlas eligibility, QC, or inferential statistics.\n",
        encoding="utf-8"
    )

    progress("DONE - graph package complete.")
    print("Output folder:", outdir, flush=True)
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
