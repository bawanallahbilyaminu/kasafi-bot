"""Extract 'Capital Expenditure by Project' (pages 49-75) into SQLite table `projects`.

Cells in this section overflow into each other, so words get interleaved.  We rebuild
cell text from the PDF content-stream order of characters (each Excel cell is written
as one run), then attach wrapped cell lines to the nearest numeric row.

Usage: python -I parse_projects.py <budget.pdf> <db.sqlite> [first_page last_page]
"""
import re
import sqlite3
import sys

import pdfplumber

NUM_RE = re.compile(r"^-?[\d,]+\.\d{2}$")
COLS = [("name", 0, 160), ("admin", 160, 250), ("economic", 250, 334),
        ("function", 334, 392), ("location", 392, 455)]
TIE_PT = 2.5  # pt: how close to midway a line must be to count as ambiguous
VALUE_COLS = ["actual_2024", "revised_2025", "perf_2025_jan_sep",
              "approved_2026", "estimate_2027", "estimate_2028", "nutrition_2026"]


def runs_of(page):
    """Split page.chars (stream order) into runs = consecutive chars on one baseline moving right."""
    runs, cur = [], []
    for ch in page.chars:
        if cur:
            prev = cur[-1]
            same_line = abs(ch["top"] - prev["top"]) < 1.5
            forward = -1.0 <= ch["x0"] - prev["x1"] < 6.0
            if not (same_line and forward):
                runs.append(cur); cur = []
        cur.append(ch)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        text = "".join(c["text"] for c in r).strip()
        if not text:
            continue
        out.append({"text": text, "x0": r[0]["x0"], "x1": r[-1]["x1"], "top": r[0]["top"]})
    return out


def col_of(x0):
    for name, a, b in COLS:
        if a <= x0 < b:
            return name
    return "num"


CODE_SPLIT = re.compile(r"(?<!\d)(\d{12}|2\d{7}|33\d{6}|7\d{4})\s*-\s*")


def code_col(code):
    if len(code) == 12:
        return "admin"
    if len(code) == 5:
        return "function"
    return "location" if code.startswith("33") else "economic"


def segments(run):
    """Split a text run into (column, text) pieces using the code patterns."""
    t = re.sub(r"\s{3,}-.*$", "", run["text"]).strip()  # drop trailing dash cells merged into the run
    parts = CODE_SPLIT.split(t)
    out = []
    head = parts[0].strip()
    if head:
        out.append((col_of(run["x0"]), head))
    for i in range(1, len(parts), 2):
        code, txt = parts[i], parts[i + 1].strip()
        out.append((code_col(code), f"{code} - {txt}"))
    return out


def parse(pdf_path, first=49, last=75):
    pdf = pdfplumber.open(pdf_path)
    projects = []
    for pno in range(first, last + 1):
        page = pdf.pages[pno - 1]
        words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
        nums = [w for w in words if w["x1"] >= 458 and (NUM_RE.match(w["text"]) or w["text"] == "-")]
        rows = []
        for w in sorted(nums, key=lambda w: w["top"]):
            if rows and abs(rows[-1]["top"] - w["top"]) < 2.0:
                rows[-1]["nums"].append(w)
            else:
                rows.append({"top": w["top"], "nums": [w], "cells": {c[0]: [] for c in COLS}})
        rows = [r for r in rows if len(r["nums"]) >= 4]
        if not rows:
            continue
        for r in runs_of(page):
            if r["x0"] >= 455:
                continue
            # the 2024 column sits right after the location text; drop numbers glued onto it
            r = dict(r, text=re.sub(r"(?:\s+(?:-?[\d,]+\.\d{2}|-))+\s*$", "", r["text"]))
            t = r["text"]
            if t.startswith("Sokoto State Government") or t.startswith("Project Name") or "Code and Description" in t \
                    or t.startswith("Total Capital Expenditure") or t.startswith("Location") or t.startswith("Description"):
                continue
            if r["top"] < rows[0]["top"] - 20:
                continue
            nearest = min(rows, key=lambda row: abs(row["top"] - r["top"]))
            # a wrapped name line that starts in lowercase ("machines for ...", "for Premier Hospital ...")
            # continues the project ABOVE it, even when it sits closer to the next row
            # only when the line sits (almost) midway between two rows, i.e. the ambiguous case
            if col_of(r["x0"]) == "name" and r["text"][:1].islower() and nearest["top"] > r["top"]:
                above = [row for row in rows if row["top"] < r["top"] - 1]
                if above:
                    prev = max(above, key=lambda row: row["top"])
                    if abs(r["top"] - prev["top"]) - abs(nearest["top"] - r["top"]) < TIE_PT:
                        nearest = prev
            for c, txt in segments(r):
                if c == "num":
                    continue
                nearest["cells"][c].append((r["top"], r["x0"], txt))
        for row in rows:
            rec = {"page": pno}
            for c, _, _ in COLS:
                parts = sorted(row["cells"][c])
                rec[c] = re.sub(r"\s+", " ", " ".join(p[2] for p in parts)).strip()
            rec["nums"] = sorted(((n["x1"], n["text"]) for n in row["nums"]))
            projects.append(rec)
    return projects


def to_num(t):
    return 0.0 if t == "-" else float(t.replace(",", ""))


def assign(projects):
    xs = sorted(x for p in projects for x, t in p["nums"] if t != "-")
    anchors, cl = [], []
    for x in xs:
        if cl and x - cl[-1] > 15:
            anchors.append(sum(cl) / len(cl)); cl = []
        cl.append(x)
    anchors.append(sum(cl) / len(cl))
    if len(anchors) == 5:  # 2024 actuals column is all dashes: add virtual anchor on the left
        anchors.insert(0, anchors[0] - (anchors[1] - anchors[0]))
    print("anchors", [round(a) for a in anchors])
    for p in projects:
        vals = [None] * len(anchors)
        for x, t in p["nums"]:
            i = min(range(len(anchors)), key=lambda k: abs(anchors[k] - x))
            if vals[i] is None:
                vals[i] = to_num(t)
        p["values"] = (vals + [None] * 7)[:7]
    return projects


def split_code(s):
    m = re.match(r"^(\d+)\s*-\s*(.*)$", s)
    return (m.group(1), m.group(2).strip()) if m else ("", s)


def main(pdf_path, db_path, first=49, last=75):
    projects = assign(parse(pdf_path, first, last))
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS projects")
    con.execute("""CREATE TABLE projects (
        id INTEGER PRIMARY KEY, project TEXT, mda_code TEXT, mda_name TEXT, economic_code TEXT, economic_name TEXT,
        function_code TEXT, function_name TEXT, location_code TEXT, location_name TEXT,
        actual_2024 REAL, revised_2025 REAL, perf_2025_jan_sep REAL, approved_2026 REAL,
        estimate_2027 REAL, estimate_2028 REAL, nutrition_2026 REAL, source_page INTEGER)""")
    for p in projects:
        if not p["name"] and not p["admin"]:  # the "Total Capital Expenditure" row
            continue
        m = re.match(r"^0\s*0?(\d{12}) - (.*)$", p["name"])
        if m and not p["admin"]:  # source row has project name "0" (no description)
            p["admin"] = f"{m.group(1)} - {m.group(2)}"
            p["name"] = "(project description missing in budget document)"
        p["location"] = re.sub(r"(?:\s+(?:-?[\d,]+\.\d{2}|-))+\s*$", "", p["location"])
        a = split_code(p["admin"]); e = split_code(p["economic"]); f = split_code(p["function"]); l = split_code(p["location"])
        con.execute("INSERT INTO projects (project, mda_code, mda_name, economic_code, economic_name, function_code, function_name,"
                    " location_code, location_name, actual_2024, revised_2025, perf_2025_jan_sep, approved_2026, estimate_2027,"
                    " estimate_2028, nutrition_2026, source_page) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["name"], *a, *e, *f, *l, *p["values"], p["page"]))
    con.commit()
    # full-text index over project descriptions (+ MDA / economic / location names) for search
    con.execute("DROP TABLE IF EXISTS projects_fts")
    con.execute("CREATE VIRTUAL TABLE projects_fts USING fts5(project, mda_name, economic_name, location_name, "
                "content='projects', content_rowid='id', tokenize='porter unicode61')")
    con.execute("INSERT INTO projects_fts(rowid, project, mda_name, economic_name, location_name) "
                "SELECT id, project, mda_name, economic_name, location_name FROM projects")
    con.commit()
    n, tot = con.execute("SELECT count(*), sum(approved_2026) FROM projects").fetchone()
    print(f"projects: {n}  sum approved_2026: {tot:,.2f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0], args[1], *(int(a) for a in args[2:4]))
