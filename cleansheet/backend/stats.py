"""Anonymous aggregate counters.

What is stored: four running totals (completed cleanings, rows in, rows out,
changes applied). What is NEVER stored: file contents, filenames, IPs,
timestamps of individual jobs, or anything identifying a user.

Backend: SQLite file, one table, upserts under a lock. Location defaults to
the OS temp dir and can be overridden with CLEANSHEET_STATS_PATH (used by
tests, and by deployments with a persistent disk).

Honesty notes:
- Counts only ever go up while the database file lives. On hosts with an
  ephemeral filesystem (e.g. free-tier redeploys), the file can be wiped and
  counting restarts from zero. It never inflates, only resets.
- The public counter in the frontend stays hidden until totals cross a
  threshold, so early low numbers are never displayed as social proof.
"""

from __future__ import annotations

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
    return con


def record_cleaning(rows_before: int, rows_after: int, changes_applied: int) -> None:
    """Add one completed cleaning job to the totals. Must never raise."""
    try:
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
    except Exception:
        # Statistics must never break cleaning.
        pass


def get_stats() -> dict[str, int]:
    """Return current totals (zeros when nothing recorded yet)."""
    totals = {"jobs_completed": 0, "rows_in": 0, "rows_out": 0, "changes_applied": 0}
    try:
        with _lock, _connect() as con:
            for name, value in con.execute("SELECT name, value FROM counters"):
                if name in totals:
                    totals[name] = int(value)
    except Exception:
        pass
    return totals
