"""Interaction log: the evidence of real-world use (NAIC: 50+ documented user interactions).

Stores a salted hash of the user id (never the phone number / Telegram id), what was asked,
how it was understood, which facts were used, the answer, timings and user feedback.
"""
import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone

from . import config

SCHEMA = """CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT, channel TEXT, user_hash TEXT, input_type TEXT, audio_seconds REAL,
    transcript TEXT, natlas_understanding TEXT, english TEXT, lang TEXT, intent TEXT, entities TEXT,
    facts TEXT, answer TEXT, answer_source TEXT, grounding_fail TEXT,
    ms_asr INTEGER, ms_understand INTEGER, ms_retrieve INTEGER, ms_write INTEGER, ms_total INTEGER,
    asr_model TEXT, llm_model TEXT, feedback INTEGER, feedback_ts TEXT, error TEXT)"""


def user_hash(channel, uid):
    return hashlib.sha256(f"{config.LOG_SALT}|{channel}|{uid}".encode()).hexdigest()[:16]


class LogStore:
    def __init__(self, path=config.LOG_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.execute(SCHEMA)
        self.con.commit()
        self._lock = threading.Lock()

    def add(self, rec: dict) -> int:
        rec = dict(rec)
        rec.setdefault("ts_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        for k in ("entities", "facts", "natlas_understanding"):
            if k in rec and not isinstance(rec[k], str):
                rec[k] = json.dumps(rec[k], ensure_ascii=False, default=str)
        cols = ", ".join(rec)
        q = ", ".join("?" for _ in rec)
        with self._lock:
            cur = self.con.execute(f"INSERT INTO interactions ({cols}) VALUES ({q})", list(rec.values()))
            self.con.commit()
            return cur.lastrowid

    def feedback(self, interaction_id, value):
        with self._lock:
            self.con.execute("UPDATE interactions SET feedback=?, feedback_ts=? WHERE id=?",
                             (value, datetime.now(timezone.utc).isoformat(timespec="seconds"), interaction_id))
            self.con.commit()

    def last_for_user(self, uhash):
        r = self.con.execute("SELECT id FROM interactions WHERE user_hash=? ORDER BY id DESC LIMIT 1", (uhash,)).fetchone()
        return r[0] if r else None
