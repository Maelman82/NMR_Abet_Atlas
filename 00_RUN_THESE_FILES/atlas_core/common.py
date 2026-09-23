from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


def norm_text(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def norm_key(x: Any) -> str:
    return norm_text(x).lower()


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        try:
            v = float(x)
            return v if math.isfinite(v) else None
        except Exception:
            return None
    s = str(x).strip().replace(",", ".")
    if not s or s.lower() in {"none", "null", "nan"}:
        return None
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except ValueError:
        return None


def fast_file_fingerprint(path: Path) -> str:
    """Fast cache key based on path, size, and nanosecond mtime.

    Deliberately avoids hashing multi-GB ABET files on every launch. If a file is
    replaced while preserving both size and mtime (unusual), use --force-rebuild.
    """
    st = path.stat()
    payload = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8", "surrogatepass")
    return hashlib.sha256(payload).hexdigest()[:20]


def source_project_hint(filename: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", " ", Path(filename).stem.lower()).strip()
    if re.search(r"(^|\s)(vac|vaccine|sham)(\s|$)", stem) or "vaccine" in stem:
        return "Vaccine"
    if re.search(r"(^|\s)(mab|lecanemab|pbs|lec)(\s|$)", stem) or "lecanemab" in stem:
        return "Lecanemab"
    return ""


def classify_schedule(schedule: str) -> tuple[str, str]:
    """Return conservative (task_hint, session_type_hint) from schedule name only."""
    s = norm_key(schedule)
    task = "Unknown"
    if any(k in s for k in ("icpt", "rcpt", " cpt", "cpt ")) or s.startswith("cpt"):
        task = "CPT"
    elif any(k in s for k in ("5csrt", "5-csr", "5 choice", "five choice")):
        task = "5CSRTT"
    elif any(k in s for k in ("pvd", "visual discrimination", "pairwise visual")):
        task = "PVD"
    elif "tunl" in s:
        task = "TUNL"
    elif re.search(r"(^|\W)ld($|\W)", s) or "location discrimination" in s:
        task = "LD"

    session_type = "Other/Unclassified"
    if "probe 2b" in s or "probe2b" in s:
        session_type = "Probe 2b"
    elif re.search(r"stage\s*4", s):
        session_type = "Stage 4"
    elif re.search(r"stage\s*3", s):
        session_type = "Stage 3"
    elif re.search(r"stage\s*2", s):
        session_type = "Stage 2"
    elif re.search(r"stage\s*1", s):
        session_type = "Stage 1"
    elif any(k in s for k in ("habituation", "habituation", " habituation", "hab ")):
        session_type = "Habituation"
    elif any(k in s for k in ("pretrain", "pre-train", "pre train")):
        session_type = "Pretraining"
    elif "reversal" in s:
        session_type = "Reversal"
    elif "baseline" in s:
        session_type = "Baseline"
    elif "probe" in s:
        session_type = "Probe"
    elif "training" in s or "train" in s:
        session_type = "Training"
    return task, session_type


def best_datetime(*values: Any) -> str:
    """Normalize common ABET date strings to ISO where possible; preserve otherwise."""
    for value in values:
        s = norm_text(value)
        if not s:
            continue
        # ISO first
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat(sep="T")
        except Exception:
            pass
        for fmt in (
            "%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f", "%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(s, fmt).isoformat(sep="T")
            except Exception:
                continue
        return s
    return ""


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) and math.isfinite(v) else v) for k, v in row.items()})


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
