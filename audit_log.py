import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "provenance_guard.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                text TEXT NOT NULL,
                attribution TEXT,
                confidence REAL,
                llm_score REAL,
                stylometric_score REAL,
                label TEXT,
                status TEXT DEFAULT 'classified',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                content_id TEXT NOT NULL,
                creator_id TEXT,
                timestamp TEXT NOT NULL,
                attribution TEXT,
                confidence REAL,
                llm_score REAL,
                stylometric_score REAL,
                label TEXT,
                status TEXT,
                appeal_reasoning TEXT,
                extra TEXT
            )
        """)


def save_content(
    content_id: str,
    creator_id: str,
    text: str,
    attribution: str,
    confidence: float,
    llm_score: float,
    stylometric_score: float,
    label: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO content
               (content_id, creator_id, text, attribution, confidence,
                llm_score, stylometric_score, label, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'classified', ?)""",
            (
                content_id,
                creator_id,
                text,
                attribution,
                confidence,
                llm_score,
                stylometric_score,
                label,
                now,
            ),
        )
        conn.execute(
            """INSERT INTO audit_log
               (entry_type, content_id, creator_id, timestamp, attribution,
                confidence, llm_score, stylometric_score, label, status)
               VALUES ('classification', ?, ?, ?, ?, ?, ?, ?, ?, 'classified')""",
            (
                content_id,
                creator_id,
                now,
                attribution,
                confidence,
                llm_score,
                stylometric_score,
                label,
            ),
        )


def update_status(content_id: str, status: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE content SET status = ? WHERE content_id = ?",
            (status, content_id),
        )
        return cur.rowcount > 0


def get_content(content_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM content WHERE content_id = ?", (content_id,)
        ).fetchone()
        return dict(row) if row else None


def log_appeal(content_id: str, creator_id: str, reasoning: str) -> dict:
    content = get_content(content_id)
    if not content:
        return {}

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (entry_type, content_id, creator_id, timestamp, attribution,
                confidence, llm_score, stylometric_score, label, status,
                appeal_reasoning)
               VALUES ('appeal', ?, ?, ?, ?, ?, ?, ?, ?, 'under_review', ?)""",
            (
                content_id,
                creator_id,
                now,
                content["attribution"],
                content["confidence"],
                content["llm_score"],
                content["stylometric_score"],
                content["label"],
                reasoning,
            ),
        )
    return content


def get_log_entries(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT entry_type, content_id, creator_id, timestamp, attribution,
                      confidence, llm_score, stylometric_score, label, status,
                      appeal_reasoning
               FROM audit_log ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    entries = []
    for row in rows:
        entry = {
            "entry_type": row["entry_type"],
            "content_id": row["content_id"],
            "creator_id": row["creator_id"],
            "timestamp": row["timestamp"],
            "attribution": row["attribution"],
            "confidence": row["confidence"],
            "llm_score": row["llm_score"],
            "stylometric_score": row["stylometric_score"],
            "label": row["label"],
            "status": row["status"],
        }
        if row["appeal_reasoning"]:
            entry["appeal_reasoning"] = row["appeal_reasoning"]
        entries.append(entry)
    return entries
