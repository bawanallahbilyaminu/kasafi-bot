"""Extract the Sokoto State 2026 Approved Budget PDF (Excel export) into SQLite.

Classification tables (admin / economic / functional / location / programme,
revenue and expenditure) are parsed from word positions with pdfplumber.
Every row keeps its source page so the bot can cite it.

Usage: python -I parse_budget.py <budget.pdf> <out.sqlite>                       (2026 budget -> line_items)
       python -I parse_budget.py <budget.pdf> <out.sqlite> --year 2025 --table line_items_2025 --stop 30 --no-detail
"""
import re
import sqlite3
import sys
from collections import defaultdict

import pdfplumber

NUM_RE = re.compile(r"^\(?-?[\d,]+\.\d{2}\)?$")
DASH = {"-", "–"}
CODE_RE = re.compile(r"^\d{1,14}$")
TITLE_RE = re.compile(r"Sokoto State Government 20\d\d Approved Budget")
TABLE = "line_items"
YEAR = 2026
STOP_PAGE = 210        # 2026 budget: per-programme project listing starts here (not parsed)
DETAIL_FROM = 82       # 2026 budget: per-MDA economic detail pages start here (None = document has none)


def value_cols(year):
    y = year
    return [f"actual_{y-2}", f"revised_{y-1}", f"perf_{y-1}_jan_sep", f"approved_{y}", f"estimate_{y+1}",
            f"estimate_{y+2}", f"nutrition_{y}"]


VALUE_COLS = value_cols(YEAR)

# Sections handled by the generic parser -> (table kind, measure)
SECTION_MAP = {
    "Total Revenue (including Capital Receipts) by Administrative Classification": ("revenue_admin", "total_revenue"),
    "Recurrent Revenue by Administrative Classification": ("revenue_admin", "recurrent_revenue"),
    "Capital Receipts by Administrative Classification": ("revenue_admin", "capital_receipts"),
    "Revenue by Economic Classification": ("revenue_economic", "total_revenue"),
    "Total Expenditure by Administrative Classification": ("exp_admin", "total"),
    "Personnel Expenditure by Administrative Classification": ("exp_admin", "personnel"),
    "Other Non-Debt Recurrent Expenditure by Administrative Classification": ("exp_admin", "overhead"),
    "Other Non-Debt Recurrent Expenditure by Fund Source": ("exp_admin", "overhead"),  # 2025 budget's (mis)title
    "Debt Service Expenditure by Administrative Classification": ("exp_admin", "debt_service"),
    "Capital Expenditure by Administrative Classification": ("exp_admin", "capital"),
    "Expenditure by Economic Classification": ("exp_economic", "total"),
    "Total Expenditure by Functional Classification": ("exp_function", "total"),
    "Personnel Expenditure by Functional Classification": ("exp_function", "personnel"),
    "Other Non-Debt Recurrent Expenditure by Functional Classification": ("exp_function", "overhead"),
    "Debt Service Expenditure by Functional Classification": ("exp_function", "debt_service"),
    "Capital Expenditure by Functional Classification": ("exp_function", "capital"),
    "Total Expenditure by Location": ("exp_location", "total"),
    "Personnel Expenditure by Location": ("exp_location", "personnel"),
    "Other Non-Debt Recurrent Expenditure by Location": ("exp_location", "overhead"),
    "Debt Service Expenditure by Location": ("exp_location", "debt_service"),
    "Capital Expenditure by Location": ("exp_location", "capital"),
    "Total Expenditure by Programme (Sector, Objective and Programme)": ("exp_programme", "total"),
    "Personnel Expenditure by Programme (Sector, Objective and Programme)": ("exp_programme", "personnel"),
    "Other Non-Debt Recurrent Expenditure by Programme (Sector, Objective and Programme)": ("exp_programme", "overhead"),
    "Debt Service Expenditure by Programme (Sector, Objective and Programme)": ("exp_programme", "debt_service"),
    "Capital Expenditure by Programme (Sector, Objective and Programme)": ("exp_programme", "capital"),
    "Health Capital Expenditure by Programme (Sector, Objective and Programme)": ("health_programme", "capital"),
    "Basic Education Expenditure by Administrative Classification": ("basic_edu_admin", "total"),
    "Basic Education Expenditure by Economic Classification": ("basic_edu_economic", "total"),
    "Basic Education Expenditure by Functional Classification": ("basic_edu_function", "total"),
    "Basic Education Expenditure by Programme Classification": ("basic_edu_programme", "total"),
    "Primary Health Expenditure by Administrative Classification": ("phc_admin", "total"),
    "Primary Health Expenditure by Economic Classification": ("phc_economic", "total"),
    "Primary Health Expenditure by Functional Classification": ("phc_function", "total"),
    "Primary Health Expenditure by Programme Classification": ("phc_programme", "total"),
}
SKIP_SECTIONS = ("Summary", "Revenue by MDA", "Expenditure by MDA", "Revenue and Expenditure by Fund",
                 "Capital Expenditure by Project", "Basic Education Capital Expenditure by Project",
                 "Primary Health Capital Expenditure by Project", "by MDA by Main Economic")


def to_num(t):
    if t in DASH:
        return 0.0
    neg = t.startswith("(") or t.startswith("-")
    v = float(t.strip("()").replace(",", "").lstrip("-"))
    return -v if neg else v


def lines_of(page):
    words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
    words.sort(key=lambda w: (round(w["top"]), w["x0"]))
    lines, cur, cur_top = [], [], None
    for w in words:
        if cur_top is None or abs(w["top"] - cur_top) > 2.5:
            if cur:
                lines.append(sorted(cur, key=lambda w: w["x0"]))
            cur, cur_top = [w], w["top"]
        else:
            cur.append(w)
    if cur:
        lines.append(sorted(cur, key=lambda w: w["x0"]))
    # re-join numbers that the PDF split into fragments, e.g. "9,700,000 . 0 0"
    frag = re.compile(r"^[\d,.]+$")
    merged = []
    for ln in lines:
        out = []
        for w in ln:
            if out and w["x0"] > 230 and frag.match(w["text"]) and frag.match(out[-1]["text"]) \
                    and w["x0"] - out[-1]["x1"] < 3.0 and not NUM_RE.match(out[-1]["text"]):
                out[-1] = dict(out[-1], text=out[-1]["text"] + w["text"], x1=w["x1"])
            else:
                out.append(w)
        merged.append(out)
    return merged


def section_name(text):
    return TITLE_RE.split(text, 1)[1].strip(" -")


def classify_section(name):
    for k in sorted(SECTION_MAP, key=len, reverse=True):
        if name.startswith(k):
            return SECTION_MAP[k]
    return None


def is_numeric_tok(t):
    return bool(NUM_RE.match(t)) or t in DASH


def parse(pdf_path):
    pdf = pdfplumber.open(pdf_path)
    rows = []  # dicts
    section = None
    mda_ctx = None  # for MDA detail pages
    in_detail = False
    pending = None  # current row being accumulated

    def flush():
        nonlocal pending
        if pending and pending["nums"]:
            rows.append(pending)
        pending = None

    for pno, page in enumerate(pdf.pages, 1):
        if STOP_PAGE and pno >= STOP_PAGE:  # project listings are handled in parse_projects.py
            break
        for ln in lines_of(page):
            text = " ".join(w["text"] for w in ln)
            if TITLE_RE.search(text):
                flush()
                name = section_name(text)
                section = None if any(name.startswith(s) or s in name for s in SKIP_SECTIONS) else classify_section(name)
                in_detail = False
                continue
            # MDA detail block header: "<12-digit code> <MDA name>" with no numbers, from page 82
            first = ln[0]["text"]
            if DETAIL_FROM and pno >= DETAIL_FROM and re.match(r"^\d{12}$", first) and not any(is_numeric_tok(w["text"]) for w in ln[1:]):
                flush()
                mda_ctx = (first, " ".join(w["text"] for w in ln[1:]))
                in_detail = True
                section = ("mda_detail", None)
                continue
            if section is None:
                continue
            if first in ("Code",) or "January" in text or text.startswith("2025 Performance") or "Out-Year" in text and not any(NUM_RE.match(w["text"]) for w in ln):
                continue
            is_start = (CODE_RE.match(first) and ln[0]["x0"] < 100) or first.startswith("Total")
            if is_start:
                flush()
                code = first if CODE_RE.match(first) else ""
                pending = {"page": pno, "kind": section[0], "measure": section[1], "code": code,
                           "name_parts": [], "nums": [], "mda": mda_ctx if section[0] == "mda_detail" else None}
                rest = ln[1:] if code else ln
            else:
                if pending is None:
                    continue
                rest = ln
            for w in rest:
                t = w["text"]
                if is_numeric_tok(t) and (w["x0"] > 230 or (NUM_RE.match(t) and w["x0"] > 170)):
                    # a leading digit of the first number sometimes sticks to the name ("Development2" + "97,000,000.00")
                    if not pending["nums"] and pending["name_parts"] and t not in DASH:
                        m = re.match(r"^(.*[A-Za-z)])(\d{1,3})$", pending["name_parts"][-1])
                        if m:
                            pending["name_parts"][-1] = m.group(1)
                            pending["glue"] = (m.group(2), w["x1"])
                            t = m.group(2) + t
                    pending["nums"].append((w["x1"], t))
                else:
                    pending["name_parts"].append(t)
        # rows don't span pages
        flush()
    return rows


def assign_columns(rows):
    """Map each row's numeric tokens to value columns using x anchors per (kind, page-layout)."""
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[(r["kind"], r["measure"])].append(r)
    out = []
    for key, rs in by_kind.items():
        xs = sorted(x for r in rs for x, t in r["nums"] if t not in DASH)
        anchors, cl = [], []
        for x in xs:
            if cl and x - cl[-1] > 18:
                anchors.append(sum(cl) / len(cl)); cl = []
            cl.append(x)
        if cl:
            anchors.append(sum(cl) / len(cl))
        if len(anchors) == 5:
            # 2024 actuals column is all dashes in these sections: add a virtual anchor on the left
            anchors.insert(0, anchors[0] - (anchors[1] - anchors[0]))
        for r in rs:
            vals = [None] * len(anchors)
            for x, t in r["nums"]:
                i = min(range(len(anchors)), key=lambda k: abs(anchors[k] - x))
                if vals[i] is None:
                    vals[i] = to_num(t)
            r["values"] = vals
            r["ncols"] = len(anchors)
            if r.get("glue"):
                digits, gx = r["glue"]
                r["glue_col"] = min(range(len(anchors)), key=lambda k: abs(anchors[k] - gx))
            out.append(r)
    return out


def resolve_glue(con):
    """A digit glued to a name is either part of the first number or a footnote mark in the name.
    Keep whichever reading makes the admin hierarchy (MDAs -> ministry) add up."""
    flagged = con.execute(f"SELECT id, kind, measure, code, name, glue_digits, glue_col FROM {TABLE} "
                          "WHERE glue_digits IS NOT NULL").fetchall()
    for rid, kind, measure, code, name, digits, gcol in flagged:
        col = VALUE_COLS[gcol]
        val = con.execute(f"SELECT {col} FROM {TABLE} WHERE id=?", (rid,)).fetchone()[0]
        mag = 10 ** len(f"{int(val):d}") // 10 ** (len(f"{int(val):d}") - len(digits)) if val else 0
        alt = float(str(int(val))[len(digits):] or 0) + (val - int(val)) if val else val
        ok_with = ok_without = None
        if len(code) == 12 and code[4:] != "0" * 8:  # MDA: compare siblings sum with ministry
            parent = con.execute(f"SELECT {col} FROM {TABLE} WHERE kind=? AND measure IS ? AND code=?",
                                 (kind, measure, code[:4] + "0" * 8)).fetchone()
            sib = con.execute(f"SELECT sum(coalesce({col},0)) FROM {TABLE} WHERE kind=? AND measure IS ? AND length(code)=12 "
                              "AND substr(code,1,4)=? AND substr(code,5)!='00000000'", (kind, measure, code[:4])).fetchone()[0]
            if parent:
                ok_with = abs(sib - parent[0]) < 1
                ok_without = abs(sib - val + alt - parent[0]) < 1
        if ok_without and not ok_with:
            con.execute(f"UPDATE {TABLE} SET {col}=?, name=? WHERE id=?", (alt, name + digits, rid))
    con.commit()


def main(pdf_path, db_path):
    rows = assign_columns(parse(pdf_path))
    con = sqlite3.connect(db_path)
    con.execute(f"DROP TABLE IF EXISTS {TABLE}")
    vc = ", ".join(f"{c} REAL" for c in VALUE_COLS)
    con.execute(f"""CREATE TABLE {TABLE} (
        id INTEGER PRIMARY KEY, kind TEXT, measure TEXT, code TEXT, name TEXT, level INTEGER,
        mda_code TEXT, mda_name TEXT, {vc},
        source_page INTEGER, glue_digits TEXT, glue_col INTEGER)""")
    bad = 0
    for r in rows:
        name = " ".join(r["name_parts"]).strip()
        # undo letter-spacing artefacts: "Deve l o p m e n t" -> "Development"
        name = re.sub(r"(?<=\w) (?=\w(?: |$|\)|-))", lambda m: "", name) if re.search(r"(?:\b\w ){3,}", name) else name
        name = re.sub(r"\s*-$", "", name).strip()
        vals = r["values"]
        if r["ncols"] < 6:
            bad += 1
            continue
        vals = [0.0 if (v is None and i < r["ncols"]) else v for i, v in enumerate((vals + [None] * 7)[:7])]
        code = r["code"]
        level = len(code)
        mda = r["mda"] or (None, None)
        kind = r["kind"]
        measure = r["measure"]
        if kind == "mda_detail":
            kind = "mda_revenue_economic" if code.startswith("1") else "mda_exp_economic"
        con.execute(f"INSERT INTO {TABLE} (kind, measure, code, name, level, mda_code, mda_name, {', '.join(VALUE_COLS)}, "
                    "source_page, glue_digits, glue_col)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (kind, measure, code, name, level, mda[0], mda[1], *vals, r["page"],
                     r["glue"][0] if r.get("glue") else None, r.get("glue_col")))
    con.commit()
    resolve_glue(con)
    print("rows:", len(rows), "skipped(<6 cols):", bad)
    for k, n in con.execute(f"SELECT kind||'/'||coalesce(measure,''), count(*) FROM {TABLE} GROUP BY 1"):
        print(f"  {k:45s} {n}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf"); ap.add_argument("db")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--table", default="line_items")
    ap.add_argument("--stop", type=int, default=210)
    ap.add_argument("--detail-from", type=int, default=82)
    ap.add_argument("--no-detail", action="store_true")
    a = ap.parse_args()
    YEAR, TABLE, STOP_PAGE = a.year, a.table, a.stop
    DETAIL_FROM = None if a.no_detail else a.detail_from
    VALUE_COLS = value_cols(YEAR)
    main(a.pdf, a.db)
