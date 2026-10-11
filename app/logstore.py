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


USERS = """CREATE TABLE IF NOT EXISTS users (
    user_hash TEXT PRIMARY KEY, channel TEXT, name TEXT, organization TEXT, stage TEXT, pending TEXT,
    created_utc TEXT, completed_utc TEXT)"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def user_hash(channel, uid):
    return hashlib.sha256(f"{config.LOG_SALT}|{channel}|{uid}".encode()).hexdigest()[:16]


class LogStore:
    def __init__(self, path=config.LOG_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.execute(SCHEMA)
        self.con.execute(USERS)
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(interactions)")}
        for c, t in (("voice_reply", "INTEGER"), ("ms_tts", "INTEGER")):
            if c not in cols:
                self.con.execute(f"ALTER TABLE interactions ADD COLUMN {c} {t}")
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

    def voice_reply(self, interaction_id, ms):
        with self._lock:
            self.con.execute("UPDATE interactions SET voice_reply=1, ms_tts=? WHERE id=?", (ms, interaction_id))
            self.con.commit()

    # ---------------------------------------------------------------- users (name + organisation)
    def get_user(self, uhash):
        self.con.row_factory = sqlite3.Row
        try:
            r = self.con.execute("SELECT * FROM users WHERE user_hash=?", (uhash,)).fetchone()
        finally:
            self.con.row_factory = None
        return dict(r) if r else None

    def upsert_user(self, uhash, completed=False, **fields):
        with self._lock:
            if not self.con.execute("SELECT 1 FROM users WHERE user_hash=?", (uhash,)).fetchone():
                self.con.execute("INSERT INTO users (user_hash, created_utc) VALUES (?, ?)", (uhash, now()))
            if completed:
                fields["completed_utc"] = now()
            if fields:
                sets = ", ".join(f"{k}=?" for k in fields)
                self.con.execute(f"UPDATE users SET {sets} WHERE user_hash=?", [*fields.values(), uhash])
            self.con.commit()

    def stats(self):
        q = lambda sql, *a: self.con.execute(sql, a).fetchone()[0]
        chans = "channel IN ('telegram','whatsapp','web')"
        return {
            "interactions": q(f"SELECT count(*) FROM interactions WHERE {chans}"),
            "today": q(f"SELECT count(*) FROM interactions WHERE {chans} AND ts_utc >= date('now')"),
            "voice": q(f"SELECT count(*) FROM interactions WHERE {chans} AND input_type='voice'"),
            "natlas": q(f"SELECT count(*) FROM interactions WHERE {chans} AND answer_source='natlas'"),
            "template": q(f"SELECT count(*) FROM interactions WHERE {chans} AND answer_source='template'"),
            "thumbs_up": q(f"SELECT count(*) FROM interactions WHERE {chans} AND feedback=1"),
            "thumbs_down": q(f"SELECT count(*) FROM interactions WHERE {chans} AND feedback=-1"),
            "users": q("SELECT count(*) FROM users WHERE stage='done'"),
            "registering": q("SELECT count(*) FROM users WHERE stage!='done'"),
            "orgs": self.con.execute("SELECT coalesce(organization,'?'), count(*) FROM users WHERE stage='done' "
                                     "GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall(),
        }

    def recent(self, n=10, only_bad=False):
        where = "i.channel IN ('telegram','whatsapp','web')"
        if only_bad:
            where += " AND (i.feedback=-1 OR i.answer_source='template' OR i.error IS NOT NULL)"
        return self.con.execute(
            f"SELECT i.id, i.ts_utc, i.channel, i.input_type, coalesce(u.name,'?'), coalesce(u.organization,'?'), "
            f"i.transcript, i.intent, i.answer_source, i.grounding_fail, i.feedback, i.answer, i.error "
            f"FROM interactions i LEFT JOIN users u ON u.user_hash=i.user_hash WHERE {where} "
            f"ORDER BY i.id DESC LIMIT ?", (n,)).fetchall()

    def last_for_user(self, uhash):
        r = self.con.execute("SELECT id FROM interactions WHERE user_hash=? ORDER BY id DESC LIMIT 1", (uhash,)).fetchone()
        return r[0] if r else None
