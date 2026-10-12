"""Export the interaction log as NAIC 'real-world validation' evidence.

Writes to evidence/:
  interactions.csv      one row per user interaction (user ids are salted hashes; no names or organisation)
  summary.md            counts, voice share, latency, feedback, N-ATLaS answer rate, organisations
Also writes private/users_private.csv (names, organisation and activity per registered user) to a SEPARATE
folder, so it is never uploaded with the evidence by accident. private/ is gitignored.

Run: python scripts/export_evidence.py
"""
import csv
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402

OUT = ROOT / "evidence"
PRIVATE = ROOT / "private"
COLS = ["id", "ts_utc", "channel", "user_hash", "input_type", "audio_seconds", "transcript", "english", "lang", "intent",
        "answer_source", "grounding_fail", "ms_asr", "ms_understand", "ms_retrieve", "ms_write", "ms_total",
        "asr_model", "llm_model", "feedback", "voice_reply", "ms_tts", "organization", "answer", "error"]


def main():
    OUT.mkdir(exist_ok=True)
    con = sqlite3.connect(str(config.LOG_DB))
    con.row_factory = sqlite3.Row
    have = {r[1] for r in con.execute("PRAGMA table_info(interactions)")}
    has_users = con.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone()
    sel = ", ".join(f"i.{c}" if c in have else ("u.organization" if c == "organization" and has_users else f"NULL AS {c}")
                    for c in COLS)
    join = "LEFT JOIN users u ON u.user_hash = i.user_hash" if has_users else ""
    rows = [dict(r) for r in con.execute(f"SELECT {sel} FROM interactions i {join} "
                                         "WHERE i.channel IN ('telegram','whatsapp','web') ORDER BY i.id")]
    orgs = {}
    for r in rows:
        orgs[r["organization"] or "—"] = orgs.get(r["organization"] or "—", 0) + 1
    if has_users:
        urows = [dict(r) for r in con.execute(
            "SELECT u.name, u.organization, u.channel, u.created_utc, count(i.id) AS questions, "
            "sum(i.input_type='voice') AS voice_notes, min(i.ts_utc) AS first_question, max(i.ts_utc) AS last_question "
            "FROM users u LEFT JOIN interactions i ON i.user_hash = u.user_hash WHERE u.stage='done' "
            "GROUP BY u.user_hash ORDER BY questions DESC")]
        if urows:
            PRIVATE.mkdir(exist_ok=True)
            with open(PRIVATE / "users_private.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(urows[0]))
                w.writeheader()
                w.writerows(urows)
    with open(OUT / "interactions.csv", "w", newline="", encoding="utf-8") as f:
        # organisation stays out of the shared CSV (small organisations could identify a person); it is only
        # used for the aggregate table in summary.md
        w = csv.DictWriter(f, fieldnames=[c for c in COLS if c != "organization"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    users = len({r["user_hash"] for r in rows})
    voice = sum(r["input_type"] == "voice" for r in rows)
    by_channel = {}
    for r in rows:
        by_channel[r["channel"]] = by_channel.get(r["channel"], 0) + 1
    intents = {}
    for r in rows:
        intents[r["intent"] or "—"] = intents.get(r["intent"] or "—", 0) + 1
    fb = [r["feedback"] for r in rows if r["feedback"] is not None]
    natlas = sum(r["answer_source"] == "natlas" for r in rows)
    voice_out = sum(1 for r in rows if r.get("voice_reply"))
    answered = sum(r["answer_source"] in ("natlas", "template") for r in rows)
    lat = [r["ms_total"] for r in rows if r["ms_total"]]
    asr_lat = [r["ms_asr"] for r in rows if r["ms_asr"]]
    first = rows[0]["ts_utc"] if rows else "—"
    last = rows[-1]["ts_utc"] if rows else "—"

    md = [
        "# Kasafi Bot — real-world validation summary", "",
        f"Period: {first} → {last} (UTC)", "",
        "| Metric | Value |", "|---|---|",
        f"| Documented user interactions | **{n}** |",
        f"| Unique users (hashed) | {users} |",
        f"| Voice notes (Hausa-ASR) | {voice} ({(100 * voice / n if n else 0):.0f}%) |",
        f"| Channels | {', '.join(f'{k}: {v}' for k, v in by_channel.items())} |",
        f"| Answers also sent as a Hausa voice note | {voice_out} |",
        f"| Questions answered from budget data | {answered} |",
        f"| Answers written by N-ATLaS (passed grounding check) | {natlas} |",
        f"| Answers that fell back to verified template | {answered - natlas} |",
        f"| Feedback received | {len(fb)} (👍 {sum(1 for x in fb if x > 0)}, 👎 {sum(1 for x in fb if x < 0)}) |",
        f"| Median response time | {statistics.median(lat) / 1000 if lat else 0:.1f} s |",
        f"| Median ASR time (voice) | {statistics.median(asr_lat) / 1000 if asr_lat else 0:.1f} s |",
        "", "## Questions by type", "", "| Intent | Count |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(intents.items(), key=lambda x: -x[1])],
        "", "## Questions by organisation (self-reported at registration)", "", "| Organisation | Questions |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(orgs.items(), key=lambda x: -x[1])],
        "", "Raw log: `interactions.csv` (user ids are salted SHA-256 hashes; no phone numbers stored).",
    ]
    (OUT / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
