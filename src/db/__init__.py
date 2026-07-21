import sqlite3
from pathlib import Path

_db: sqlite3.Connection | None = None

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: str) -> sqlite3.Connection:
    global _db
    _db = sqlite3.connect(db_path, check_same_thread=False)
    _db.execute("PRAGMA journal_mode=WAL")
    _db.execute("PRAGMA foreign_keys=ON")
    _db.row_factory = sqlite3.Row
    _db.executescript(SCHEMA_PATH.read_text())
    return _db


def get_db() -> sqlite3.Connection:
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _db


# --- Context queries ---


def insert_context(*, id: str, name: str, profile: str | None):
    get_db().execute(
        "INSERT INTO contexts (id, name, profile) VALUES (?, ?, ?)",
        (id, name, profile),
    )
    get_db().commit()


def list_contexts() -> list[dict]:
    rows = get_db().execute("SELECT * FROM contexts ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def list_stopped_contexts(limit: int = 50, offset: int = 0) -> list[dict]:
    rows = (
        get_db()
        .execute(
            "SELECT * FROM contexts WHERE status != 'running' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]


def get_context(id: str) -> dict | None:
    row = get_db().execute("SELECT * FROM contexts WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


def update_context_status(id: str, status: str):
    get_db().execute(
        "UPDATE contexts SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, id),
    )
    get_db().commit()


def delete_context(id: str):
    get_db().execute("DELETE FROM contexts WHERE id = ?", (id,))
    get_db().commit()


# --- Log queries ---


def insert_log(*, context_id: str, level: str = "info", message: str):
    get_db().execute(
        "INSERT INTO logs (context_id, level, message) VALUES (?, ?, ?)",
        (context_id, level or "info", message),
    )
    get_db().commit()


def get_logs_by_context(context_id: str, limit: int = 200) -> list[dict]:
    rows = (
        get_db()
        .execute(
            "SELECT * FROM logs WHERE context_id = ? ORDER BY created_at DESC LIMIT ?",
            (context_id, limit),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]
