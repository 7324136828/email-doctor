"""SQLite-backed job registry.

Single-process access is serialized with a module-level lock; job rows persist
across backend restarts so the history screen survives reloads.
"""
import sqlite3
import threading
from datetime import datetime, timezone

from .config import settings

_LOCK = threading.Lock()

JOB_STATUSES = ("queued", "in_progress", "completed", "failed", "discarded")
TERMINAL_STATUSES = ("completed", "failed", "discarded")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    log TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    temp_dir TEXT,
    zip_path TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    source_kind TEXT NOT NULL DEFAULT 'upload',
    account_email TEXT,
    days INTEGER,
    downloaded_messages INTEGER NOT NULL DEFAULT 0,
    total_messages INTEGER,
    snapshot_available INTEGER NOT NULL DEFAULT 0,
    snapshot_at TEXT
)
"""

_MIGRATIONS = {
    "source_kind": "TEXT NOT NULL DEFAULT 'upload'",
    "account_email": "TEXT",
    "days": "INTEGER",
    "downloaded_messages": "INTEGER NOT NULL DEFAULT 0",
    "total_messages": "INTEGER",
    "snapshot_available": "INTEGER NOT NULL DEFAULT 0",
    "snapshot_at": "TEXT",
}

_UPDATABLE = {
    "filename",
    "file_size",
    "status",
    "progress",
    "stage",
    "error_message",
    "temp_dir",
    "zip_path",
    "completed_at",
    "source_kind",
    "account_email",
    "days",
    "downloaded_messages",
    "total_messages",
    "snapshot_available",
    "snapshot_at",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as conn:
        conn.execute(_SCHEMA)
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        for name, definition in _MIGRATIONS.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def create_job(
    job_id: str,
    filename: str,
    file_size: int,
    temp_dir: str,
    *,
    source_kind: str = "upload",
    account_email: str | None = None,
    days: int | None = None,
) -> dict:
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, filename, file_size, status, temp_dir, created_at,"
            " source_kind, account_email, days)"
            " VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)",
            (
                job_id,
                filename,
                file_size,
                temp_dir,
                utcnow(),
                source_kind,
                account_email,
                days,
            ),
        )
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


def get_job(job_id: str) -> dict | None:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row)


def list_jobs() -> list[dict]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def update_job(job_id: str, **fields) -> None:
    assignments = {k: v for k, v in fields.items() if k in _UPDATABLE}
    if not assignments:
        return
    clause = ", ".join(f"{k} = ?" for k in assignments)
    with _LOCK, _connect() as conn:
        conn.execute(
            f"UPDATE jobs SET {clause} WHERE id = ?",
            (*assignments.values(), job_id),
        )


def append_log(job_id: str, line: str) -> None:
    """Append a line to the job log, capping total size."""
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT log FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return
        log = (row["log"] or "") + line.rstrip("\n") + "\n"
        cap = settings.log_char_cap
        if len(log) > cap:
            log = log[-cap:]
        conn.execute("UPDATE jobs SET log = ? WHERE id = ?", (log, job_id))
