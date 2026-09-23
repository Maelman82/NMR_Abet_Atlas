from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from .common import norm_text


class AtlasError(RuntimeError):
    pass


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_lookup(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(r[0]).lower(): str(r[0]) for r in rows}


def require_table(conn: sqlite3.Connection, wanted: str) -> str:
    tables = table_lookup(conn)
    got = tables.get(wanted.lower())
    if not got:
        raise AtlasError(f"Required table {wanted!r} not found. Tables present: {sorted(tables.values())}")
    return got


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()]


def row_dicts(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    old = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.row_factory = old


def is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def ensure_cached_sqlite(input_path: Path, cached_sqlite: Path, force: bool = False) -> Path:
    """Create/reuse a persistent SQLite copy of an ABET database.

    Native SQLite inputs are copied with SQLite backup semantics. Access-style
    .ABETdb/.mdb files are converted once with abet-converter and then reused.
    """
    cached_sqlite.parent.mkdir(parents=True, exist_ok=True)
    if cached_sqlite.exists() and not force:
        return cached_sqlite
    if cached_sqlite.exists():
        cached_sqlite.unlink()

    if is_sqlite(input_path):
        src = sqlite3.connect(f"file:{input_path.resolve()}?mode=ro", uri=True)
        dst = sqlite3.connect(cached_sqlite)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        return cached_sqlite

    if input_path.suffix.lower() not in {".abetdb", ".mdb", ".db"}:
        raise AtlasError(f"Unsupported database type: {input_path.name}")

    cmd = [sys.executable, "-m", "abet_converter", "--input", str(input_path), "--output", str(cached_sqlite)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not cached_sqlite.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise AtlasError(
            "Could not convert ABET database. Install requirements with:\n"
            "  python -m pip install -r requirements.txt\n\n"
            f"Database: {input_path}\nConverter output:\n{detail}"
        )
    return cached_sqlite


def get_sessions(conn: sqlite3.Connection) -> dict[Any, dict[str, Any]]:
    """Read every ABET schedule/session plus all schedule-note metadata."""
    schedules_t = require_table(conn, "tbl_Schedules")
    notes_t = require_table(conn, "tbl_Schedule_Notes")
    sched_rows = row_dicts(conn, f"SELECT * FROM {quote_ident(schedules_t)}")
    note_rows = row_dicts(conn, f"SELECT * FROM {quote_ident(notes_t)}")

    sessions: dict[Any, dict[str, Any]] = {}
    for r in sched_rows:
        sid = r.get("SID")
        sessions.setdefault(sid, {})
        sessions[sid].update({
            "SID": sid,
            "Schedule": norm_text(r.get("SName")),
            "Machine": norm_text(r.get("SMachineName")),
            "SRunDate": norm_text(r.get("SRunDate")),
            "SFinal": r.get("SFinal"),
            "SRecCount": r.get("SRecCount"),
        })

    for r in note_rows:
        sid = r.get("SID")
        sessions.setdefault(sid, {"SID": sid})
        name = norm_text(r.get("NName"))
        if name:
            sessions[sid][name] = r.get("NValue")

    for s in sessions.values():
        s["Animal_ID"] = norm_text(s.get("Animal ID") or s.get("Animal_ID"))
        s["Schedule_Start_Time"] = norm_text(s.get("Schedule_Start_Time"))
        s.setdefault("Schedule", "")
        s.setdefault("Machine", "")
        s.setdefault("SRunDate", "")
    return sessions


def event_count(conn: sqlite3.Connection, sid: Any) -> int:
    data_t = require_table(conn, "tbl_Data")
    return int(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(data_t)} WHERE SID=?", (sid,)).fetchone()[0])


def get_events(conn: sqlite3.Connection, sid: Any) -> list[dict[str, Any]]:
    data_t = require_table(conn, "tbl_Data")
    cols = columns(conn, data_t)
    if "rowid" not in [c.lower() for c in cols]:
        q = f"SELECT rowid AS _rowid_, * FROM {quote_ident(data_t)} WHERE SID=? ORDER BY DTime, rowid"
    else:
        q = f"SELECT * FROM {quote_ident(data_t)} WHERE SID=? ORDER BY DTime"
    return row_dicts(conn, q, (sid,))
