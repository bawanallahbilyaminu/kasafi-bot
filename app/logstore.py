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
        for c, t in (("voice_reply", "INTEGER"), ("ms_tts", "INTEGER"), ("review_status", "TEXT"),
                     ("review_note", "TEXT"), ("reviewed_utc", "TEXT")):
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
        # own cursor with its own row factory: the shared connection is never changed (safe across threads)
        with self._lock:
            cur = self.con.cursor()
            cur.row_factory = sqlite3.Row
            r = cur.execute("SELECT * FROM users WHERE user_hash=?", (uhash,)).fetchone()
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
        with self._lock:
            return self._stats()

    def _stats(self):
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
        with self._lock:
            return self.con.execute(
            f"SELECT i.id, i.ts_utc, i.channel, i.input_type, coalesce(u.name,'?'), coalesce(u.organization,'?'), "
            f"i.transcript, i.intent, i.answer_source, i.grounding_fail, i.feedback, i.answer, i.error "
            f"FROM interactions i LEFT JOIN users u ON u.user_hash=i.user_hash WHERE {where} "
            f"ORDER BY i.id DESC LIMIT ?", (n,)).fetchall()

    # ---------------------------------------------------------------- admin review (web admin page)
    ADMIN_COLS = ("i.id, i.ts_utc, i.channel, i.input_type, i.audio_seconds, i.transcript, i.english, i.lang, i.intent, "
                  "i.answer_source, i.grounding_fail, i.ms_total, i.feedback, i.voice_reply, i.error, i.review_status, "
                  "i.review_note, coalesce(u.name, '') AS name, coalesce(u.organization, '') AS organization")
    PROBLEM = "(i.answer_source = 'template' OR i.grounding_fail IS NOT NULL OR i.error IS NOT NULL OR i.feedback = -1)"

    def _rows(self, sql, args):
        with self._lock:
            cur = self.con.cursor()
            cur.row_factory = sqlite3.Row
            return [dict(r) for r in cur.execute(sql, args).fetchall()]

    def admin_list(self, channel=None, view="all", q=None, limit=50, offset=0):
        where, args = ["i.channel IN ('telegram','whatsapp','web')"], []
        if channel:
            where.append("i.channel = ?"); args.append(channel)
        if view == "problems":
            where.append(self.PROBLEM)
        elif view == "down":
            where.append("i.feedback = -1")
        elif view == "unreviewed":
            where.append(f"{self.PROBLEM} AND i.review_status IS NULL")
        elif view == "issues":
            where.append("i.review_status = 'issue'")
        elif view == "voice":
            where.append("i.input_type = 'voice'")
        if q:
            where.append("(i.transcript LIKE ? OR i.answer LIKE ? OR i.english LIKE ? OR u.name LIKE ? OR u.organization LIKE ?)")
            args += [f"%{q}%"] * 5
        w = " AND ".join(where)
        base = f"FROM interactions i LEFT JOIN users u ON u.user_hash = i.user_hash WHERE {w}"
        total = self._rows(f"SELECT count(*) AS n {base}", args)[0]["n"]
        rows = self._rows(f"SELECT {self.ADMIN_COLS}, substr(i.answer, 1, 240) AS answer_preview {base} "
                          f"ORDER BY i.id DESC LIMIT ? OFFSET ?", args + [int(limit), int(offset)])
        return {"total": total, "rows": rows}

    def admin_get(self, iid):
        rows = self._rows(f"SELECT {self.ADMIN_COLS}, i.answer, i.facts, i.entities, i.natlas_understanding, i.ms_asr, "
                          "i.ms_understand, i.ms_retrieve, i.ms_write, i.ms_tts, i.asr_model, i.llm_model, i.feedback_ts, "
                          "i.reviewed_utc FROM interactions i LEFT JOIN users u ON u.user_hash = i.user_hash WHERE i.id = ?",
                          (int(iid),))
        return rows[0] if rows else None

    def admin_review(self, iid, status, note):
        with self._lock:
            n = self.con.execute("UPDATE interactions SET review_status=?, review_note=?, reviewed_utc=? WHERE id=?",
                                 (status or None, (note or "").strip()[:2000] or None, now() if status else None,
                                  int(iid))).rowcount
            self.con.commit()
        return n

    def admin_stats(self):
        s = self.stats()
        g = lambda sql: self._rows(sql, ())
        chans = "channel IN ('telegram','whatsapp','web')"
        s["by_channel"] = g(f"SELECT channel AS k, count(*) AS n FROM interactions WHERE {chans} GROUP BY 1 ORDER BY 2 DESC")
        s["by_intent"] = g(f"SELECT coalesce(intent,'—') AS k, count(*) AS n FROM interactions WHERE {chans} "
                           "GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
        s["problems"] = g(f"SELECT count(*) AS n FROM interactions i WHERE i.{chans} AND {self.PROBLEM}")[0]["n"]
        s["unreviewed"] = g(f"SELECT count(*) AS n FROM interactions i WHERE i.{chans} AND {self.PROBLEM} "
                            "AND i.review_status IS NULL")[0]["n"]
        s["open_issues"] = g(f"SELECT count(*) AS n FROM interactions WHERE {chans} AND review_status='issue'")[0]["n"]
        s["median_ms"] = (g(f"SELECT ms_total AS v FROM interactions WHERE {chans} AND ms_total IS NOT NULL "
                            "ORDER BY ms_total LIMIT 1 OFFSET (SELECT count(*)/2 FROM interactions "
                            f"WHERE {chans} AND ms_total IS NOT NULL)") or [{"v": None}])[0]["v"]
        s["orgs"] = [{"k": o, "n": c} for o, c in s["orgs"]]
        return s

    def last_for_user(self, uhash):
        with self._lock:
            r = self.con.execute("SELECT id FROM interactions WHERE user_hash=? ORDER BY id DESC LIMIT 1", (uhash,)).fetchone()
        return r[0] if r else None
