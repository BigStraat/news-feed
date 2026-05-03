"""Dédoublonnage par hash d'URL avec TTL."""

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_urls (
    url_hash TEXT PRIMARY KEY,
    url      TEXT NOT NULL,
    seen_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_urls(seen_at);
"""


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@contextmanager
def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_seen(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_urls WHERE url_hash = ?", (_hash(url),)
    ).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, url: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO seen_urls (url_hash, url, seen_at) VALUES (?, ?, ?)",
        (_hash(url), url, int(time.time())),
    )


def purge_old(conn: sqlite3.Connection, ttl_days: int) -> int:
    cutoff = int(time.time()) - ttl_days * 86400
    cur = conn.execute("DELETE FROM seen_urls WHERE seen_at < ?", (cutoff,))
    return cur.rowcount
