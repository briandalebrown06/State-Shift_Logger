from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.detectors import AudioFeatures


class Storage:
    def __init__(self, database_path: str):
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    uid TEXT,
                    session_id TEXT,
                    text TEXT NOT NULL,
                    score REAL NOT NULL,
                    confidence TEXT NOT NULL,
                    markers_json TEXT NOT NULL,
                    notification_sent INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_shift_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    uid TEXT,
                    session_id TEXT,
                    source TEXT NOT NULL,
                    score REAL NOT NULL,
                    confidence TEXT NOT NULL,
                    markers_json TEXT NOT NULL,
                    context_excerpt TEXT NOT NULL,
                    omi_memory_created INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audio_features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    uid TEXT,
                    session_id TEXT,
                    sample_rate INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    rms REAL NOT NULL,
                    peak REAL NOT NULL,
                    zero_crossing_rate REAL NOT NULL,
                    estimated_pitch_hz REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_cooldowns (
                    uid TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    last_sent_at TEXT NOT NULL,
                    PRIMARY KEY (uid, session_id)
                )
                """
            )

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_transcript_event(
        self,
        uid: str | None,
        session_id: str | None,
        text: str,
        score: float,
        confidence: str,
        markers: list[dict[str, Any]],
        notification_sent: bool = False,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO transcript_events
                (created_at, uid, session_id, text, score, confidence, markers_json, notification_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.now_iso(),
                    uid,
                    session_id,
                    text,
                    score,
                    confidence,
                    json.dumps(markers, ensure_ascii=False),
                    1 if notification_sent else 0,
                ),
            )
            return int(cur.lastrowid)

    def save_state_shift_log(
        self,
        uid: str | None,
        session_id: str | None,
        source: str,
        score: float,
        confidence: str,
        markers: list[dict[str, Any]],
        context_excerpt: str,
        omi_memory_created: bool = False,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO state_shift_logs
                (created_at, uid, session_id, source, score, confidence, markers_json, context_excerpt, omi_memory_created)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.now_iso(),
                    uid,
                    session_id,
                    source,
                    score,
                    confidence,
                    json.dumps(markers, ensure_ascii=False),
                    context_excerpt,
                    1 if omi_memory_created else 0,
                ),
            )
            return int(cur.lastrowid)

    def recent_texts(self, uid: str | None, session_id: str | None, limit: int = 5) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT text
                FROM transcript_events
                WHERE (? IS NULL OR uid = ?)
                  AND (? IS NULL OR session_id = ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (uid, uid, session_id, session_id, limit),
            ).fetchall()
        return [str(row["text"]) for row in reversed(rows)]

    def save_audio_features(
        self,
        uid: str | None,
        session_id: str | None,
        sample_rate: int,
        features: AudioFeatures,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audio_features
                (created_at, uid, session_id, sample_rate, duration_seconds, rms, peak, zero_crossing_rate, estimated_pitch_hz)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.now_iso(),
                    uid,
                    session_id,
                    sample_rate,
                    features.duration_seconds,
                    features.rms,
                    features.peak,
                    features.zero_crossing_rate,
                    features.estimated_pitch_hz,
                ),
            )
            return int(cur.lastrowid)

    def previous_audio_features(self, uid: str | None, session_id: str | None) -> AudioFeatures | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM audio_features
                WHERE (? IS NULL OR uid = ?)
                  AND (? IS NULL OR session_id = ?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (uid, uid, session_id, session_id),
            ).fetchone()

        if not row:
            return None

        return AudioFeatures(
            duration_seconds=float(row["duration_seconds"]),
            rms=float(row["rms"]),
            peak=float(row["peak"]),
            zero_crossing_rate=float(row["zero_crossing_rate"]),
            estimated_pitch_hz=float(row["estimated_pitch_hz"]) if row["estimated_pitch_hz"] is not None else None,
        )

    def notification_allowed(self, uid: str | None, session_id: str | None, cooldown_seconds: int) -> bool:
        key_uid = uid or "unknown"
        key_session = session_id or "unknown"

        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT last_sent_at
                FROM notification_cooldowns
                WHERE uid = ? AND session_id = ?
                """,
                (key_uid, key_session),
            ).fetchone()

            if row:
                try:
                    last = datetime.fromisoformat(row["last_sent_at"])
                except ValueError:
                    last = datetime.now(timezone.utc) - timedelta(days=1)
                if datetime.now(timezone.utc) - last < timedelta(seconds=cooldown_seconds):
                    return False

            conn.execute(
                """
                INSERT INTO notification_cooldowns (uid, session_id, last_sent_at)
                VALUES (?, ?, ?)
                ON CONFLICT(uid, session_id) DO UPDATE SET last_sent_at = excluded.last_sent_at
                """,
                (key_uid, key_session, self.now_iso()),
            )
            return True

    def get_logs(self, uid: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM state_shift_logs
                WHERE (? IS NULL OR uid = ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (uid, uid, limit),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["markers"] = json.loads(item.pop("markers_json"))
            except json.JSONDecodeError:
                item["markers"] = []
            item["omi_memory_created"] = bool(item["omi_memory_created"])
            results.append(item)
        return results

    def prune_old(self, retention_days: int) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()
        deleted: dict[str, int] = {}
        with self.connect() as conn:
            for table in ["transcript_events", "state_shift_logs", "audio_features", "notification_cooldowns"]:
                cur = conn.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff_iso,))
                deleted[table] = cur.rowcount
        return deleted
