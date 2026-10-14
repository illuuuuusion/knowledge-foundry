"""Transactional, ordered SQLite migrations."""

from contextlib import closing
from pathlib import Path
import sqlite3


MIGRATIONS = (
    (1, (
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    )),
    (2, (
        "CREATE TABLE ingestion_manifests (id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
        "CREATE TABLE transcripts (video_id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
        "CREATE TABLE ingestion_jobs (video_id TEXT PRIMARY KEY, "
        "status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','unsupported')), "
        "attempts INTEGER NOT NULL DEFAULT 0, issue TEXT, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    )),
)


def migrate(database: Path) -> int:
    """Apply pending versions atomically; refuse databases from newer code."""
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > MIGRATIONS[-1][0]:
                raise ValueError("Database schema is newer than this application")
            for target, statements in MIGRATIONS:
                if target <= version:
                    continue
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (target,)
                )
                connection.execute(f"PRAGMA user_version = {target:d}")
                version = target
            connection.commit()
            return version
        except Exception:
            connection.rollback()
            raise
