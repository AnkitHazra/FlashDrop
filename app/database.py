import os
import sqlite3
from contextlib import contextmanager

DATA_DIR = os.getenv("DATA_DIR", ".")
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(DATA_DIR, "quickshare.sqlite3"))
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                token TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_expires_at ON files(expires_at)")
