"""Anonymous aggregate counters.

What is stored: four running totals (completed cleanings, rows in, rows out,
changes applied) plus a per-day job count. What is NEVER stored: file
contents, filenames, IPs, or anything identifying a user or a job.

Backend: SQLite file, two tiny tables, upserts under a lock. Location
defaults to the OS temp dir and can be overridden with CLEANSHEET_STATS_PATH
(used by tests, and by deployments with a persistent disk).

Honesty note: counts only ever go up while the database file lives. On hosts
with an ephemeral filesystem (e.g. free-tier redeploys), the file can be
wiped and counting restarts from zero. It never inflates, only resets — and
the frontend labels the numbers as a live beta count, so small early numbers
read as transparency, not as faked popularity.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()


def db_path() -> Path:
    """Resolve the stats database location (env override wins, no caching)."""
    override = os.environ.get("CLEANSHEET_STATS_PATH")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "cleansheet_stats.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path(), check_same_thread=False)
    con.execute(
        "CREATE TABLE IF NOT EXISTS counters("
        "name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS daily(date TEXT PRIMARY KEY, jobs INTEGER NOT NULL DEFAULT 0)"
    )
    return con


def record_cleaning(rows_before: int, rows_after: int, changes_applied: int) -> None:
    """Add one completed cleaning job to the totals. Must never raise."""
    try:
        today = datetime.date.today().isoformat()
        with _lock, _connect() as con:
            con.executemany(
                "INSERT INTO counters(name, value) VALUES(?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = counters.value + excluded.value",
                [
                    ("jobs_completed", 1),
                    ("rows_in", int(rows_before)),
                    ("rows_out", int(rows_after)),
                    ("changes_applied", int(changes_applied)),
                ],
            )
            con.execute(
                "INSERT INTO daily(date, jobs) VALUES(?, 1) "
                "ON CONFLICT(date) DO UPDATE SET jobs = daily.jobs + 1",
                (today,),
            )
    except Exception:
        # Statistics must never break cleaning.
        pass


def get_stats() -> dict[str, int]:
    """Return current totals (zeros when nothing recorded yet)."""
    totals = {"jobs_completed": 0, "rows_in": 0, "rows_out": 0, "changes_applied": 0}
    jobs_today = 0
    try:
        today = datetime.date.today().isoformat()
        with _lock, _connect() as con:
            for name, value in con.execute("SELECT name, value FROM counters"):
                if name in totals:
                    totals[name] = int(value)
            row = con.execute("SELECT jobs FROM daily WHERE date = ?", (today,)).fetchone()
            jobs_today = int(row[0]) if row else 0
    except Exception:
        pass
    return {**totals, "jobs_today": jobs_today}
