"""Dédoublonnage par hash d'URL avec TTL + keywords/settings/history."""

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

CREATE TABLE IF NOT EXISTS keywords (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    source  TEXT NOT NULL CHECK(source IN ('gnews', 'newsdata'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_history (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT NOT NULL,
    url      TEXT NOT NULL,
    source   TEXT NOT NULL,
    score    INTEGER NOT NULL,
    priority TEXT NOT NULL,
    reason   TEXT,
    sent_at  INTEGER NOT NULL
);
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


# --- Seed ---

def seed_defaults(conn: sqlite3.Connection) -> None:
    import config
    import scorer

    if conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0] == 0:
        for kw in config.GNEWS_KEYWORDS:
            conn.execute(
                "INSERT INTO keywords (keyword, source) VALUES (?, ?)",
                (kw, "gnews"),
            )
        for kw in config.NEWSDATA_KEYWORDS:
            conn.execute(
                "INSERT INTO keywords (keyword, source) VALUES (?, ?)",
                (kw, "newsdata"),
            )

    if conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        defaults = {
            "language": config.LANGUAGE,
            "min_score": str(config.MIN_SCORE),
            "max_per_query": str(config.MAX_PER_QUERY),
            "dedup_ttl_days": str(config.DEDUP_TTL_DAYS),
            "prompt": scorer.SYSTEM_PROMPT,
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)", (k, v),
            )
    conn.commit()


# --- Keywords CRUD ---

def get_keywords(conn: sqlite3.Connection, source: str | None = None) -> list[dict]:
    if source:
        rows = conn.execute(
            "SELECT id, keyword, source FROM keywords WHERE source = ? ORDER BY id",
            (source,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, keyword, source FROM keywords ORDER BY id",
        ).fetchall()
    return [{"id": r[0], "keyword": r[1], "source": r[2]} for r in rows]


def add_keyword(conn: sqlite3.Connection, keyword: str, source: str) -> None:
    conn.execute(
        "INSERT INTO keywords (keyword, source) VALUES (?, ?)", (keyword, source),
    )
    conn.commit()


def delete_keyword(conn: sqlite3.Connection, keyword_id: int) -> None:
    conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
    conn.commit()


# --- Settings ---

def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,),
    ).fetchone()
    return row[0] if row else None


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r[0]: r[1] for r in rows}


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value),
    )
    conn.commit()


# --- Notification history ---

def log_notification(
    conn: sqlite3.Connection,
    title: str,
    url: str,
    source: str,
    score: int,
    priority: str,
    reason: str | None,
) -> None:
    conn.execute(
        "INSERT INTO notification_history (title, url, source, score, priority, reason, sent_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, url, source, score, priority, reason, int(time.time())),
    )
    conn.commit()


def get_recent_notifications(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, url, source, score, priority, reason, sent_at "
        "FROM notification_history ORDER BY sent_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "title": r[1], "url": r[2], "source": r[3],
            "score": r[4], "priority": r[5], "reason": r[6], "sent_at": r[7],
        }
        for r in rows
    ]


def get_notification_stats(conn: sqlite3.Connection) -> dict:
    today_start = int(time.time()) - (int(time.time()) % 86400)
    today_count = conn.execute(
        "SELECT COUNT(*) FROM notification_history WHERE sent_at >= ?",
        (today_start,),
    ).fetchone()[0]
    avg_score = conn.execute(
        "SELECT AVG(score) FROM notification_history WHERE sent_at >= ?",
        (today_start,),
    ).fetchone()[0]
    priority_counts = conn.execute(
        "SELECT priority, COUNT(*) FROM notification_history "
        "WHERE sent_at >= ? GROUP BY priority",
        (today_start,),
    ).fetchall()
    return {
        "today_count": today_count,
        "avg_score": round(avg_score, 1) if avg_score else 0,
        "by_priority": {r[0]: r[1] for r in priority_counts},
    }
