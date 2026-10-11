"""Merge another interaction log (e.g. from the Colab backup) into the main one.

Run: python scripts/merge_logs.py path/to/other_interactions.sqlite
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402
from app.logstore import LogStore  # noqa: E402


def main(other):
    LogStore()  # ensure main db + schema exist
    con = sqlite3.connect(str(config.LOG_DB))
    con.execute("ATTACH DATABASE ? AS o", (other,))
    cols = [r[1] for r in con.execute("PRAGMA table_info(interactions)") if r[1] != "id"]
    c = ", ".join(cols)
    n = con.execute(f"INSERT INTO interactions ({c}) SELECT {c} FROM o.interactions x WHERE NOT EXISTS "
                    "(SELECT 1 FROM interactions m WHERE m.ts_utc=x.ts_utc AND m.user_hash=x.user_hash)").rowcount
    con.commit()
    print(f"merged {n} interactions")


if __name__ == "__main__":
    main(sys.argv[1])
