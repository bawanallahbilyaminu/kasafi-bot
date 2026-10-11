"""Extract Sokoto State quarterly Budget Implementation Reports (Word-exported PDFs) into SQLite.

Every report uses the same table layout:
  Code | Name | Original Budget | Revised/Final Budget | Quarter Performance | YTD Performance | % YTD | Balance

Output table `perf_items`: one row per (report, table, code), e.g. report='2025Q4'.

Usage: python -I parse_reports.py <db.sqlite> <report.pdf> [<report.pdf> ...]
       (report id is read from the PDF title lines, e.g. "Budget Performance Report 2025 Q4")
"""
import re
import sqlite3
import subprocess
import sys

TITLE_RE = re.compile(r"Budget Performance Report (20\d\d) Q([1-4]) - (.+?)\s*$")
NUM = r"-?[\d,]+\.\d{2}"
TOKEN_RE = re.compile(rf"(?<!\S)(?:{NUM}%?|-?\d+(?:\.\d+)?%|-)(?!\S)")
ROW_RE = re.compile(r"^\s*(\d{1,14})\s+(\S.*)$")
TOTAL_RE = re.compile(r"^\s*(Total\b.*)$")

UNITS = {"Administrative Classification": "admin", "Economic Classification": "economic",
         "Functional Classification": "function", "Programme Classification": "programme"}
MEASURES = {"Total": "total", "Personnel": "personnel", "Overhead": "overhead", "Other": "other", "Capital": "capital"}


def classify(title):
    if "by Project" in title:
        return None
    unit = next((v for k, v in UNITS.items() if title.endswith(k)), None)
    if not unit:
        return None
    if title.startswith("Total Revenue"):
        return f"rev_{unit}", "total"
    if title.startswith("Primary Healthcare"):
        return f"phc_{unit}", "total"
    if title.startswith("Basic Education"):
        return f"basic_edu_{unit}", "total"
    first = title.split()[0]
    if first in MEASURES and "Expenditure" in title:
        return f"exp_{unit}", MEASURES[first]
    return None


def num(t):
    if t == "-":
        return 0.0
    return float(t.rstrip("%").replace(",", ""))


def split_row(rest):
    """rest = 'Name ...   n1  n2  n3  n4  pct%  [-] balance' -> (name, [orig, rev, q, ytd], pct, balance)"""
    toks = list(TOKEN_RE.finditer(rest))
    pct_i = next((i for i, m in enumerate(toks) if m.group().endswith("%")), None)
    if pct_i is None or pct_i < 4:
        return None
    vals = toks[pct_i - 4:pct_i]
    name = rest[:vals[0].start()].strip()
    after = [m.group() for m in toks[pct_i + 1:]]
    if not after:
        bal = None
    elif after == ["-"]:
        bal = 0.0
    elif len(after) >= 2 and after[0] == "-":
        bal = -num(after[1])
    else:
        bal = num(after[-1])
    return re.sub(r"\s{2,}", " ", name), [num(m.group()) for m in vals], num(toks[pct_i].group()), bal


def parse(pdf):
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
    rows, section, report = [], None, None
    for pno, page in enumerate(text.split("\f"), 1):
        for line in page.splitlines():
            m = TITLE_RE.search(line)
            if m:
                report = f"{m.group(1)}Q{m.group(2)}"
                section = classify(m.group(3).strip())
                continue
            if not section or not report:
                continue
            m = ROW_RE.match(line)
            code, rest = (m.group(1), m.group(2)) if m else ("", None)
            if not m:
                t = TOTAL_RE.match(line)
                if not t:
                    continue
                rest = t.group(1)
            sp = split_row(rest)
            if not sp:
                continue
            name, (orig, rev, q, ytd), pct, bal = sp
            rows.append({"report": report, "year": int(report[:4]), "quarter": int(report[-1]), "kind": section[0],
                         "measure": section[1], "code": code, "name": name, "budget_original": orig,
                         "budget_revised": rev, "quarter_actual": q, "ytd_actual": ytd, "ytd_pct": pct,
                         "balance": bal, "source_page": pno, "source_file": pdf.split("/")[-1]})
    return rows


def main(db, pdfs):
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS perf_items (
        id INTEGER PRIMARY KEY, report TEXT, year INTEGER, quarter INTEGER, kind TEXT, measure TEXT, code TEXT,
        name TEXT, budget_original REAL, budget_revised REAL, quarter_actual REAL, ytd_actual REAL, ytd_pct REAL,
        balance REAL, source_page INTEGER, source_file TEXT)""")
    for pdf in pdfs:
        rows = parse(pdf)
        if not rows:
            print(f"{pdf}: no rows")
            continue
        reports = {r["report"] for r in rows}
        for rep in reports:
            con.execute("DELETE FROM perf_items WHERE report=?", (rep,))
        # the same table can be printed twice (summary + detail); keep the first occurrence of (report, kind, measure, code, name)
        seen = set()
        n = 0
        for r in rows:
            k = (r["report"], r["kind"], r["measure"], r["code"], r["name"] if not r["code"] else "")
            if k in seen:
                continue
            seen.add(k)
            con.execute(f"INSERT INTO perf_items ({', '.join(r)}) VALUES ({', '.join('?' for _ in r)})", list(r.values()))
            n += 1
        con.commit()
        print(f"{pdf.split('/')[-1]}: {sorted(reports)} {n} rows")
    con.execute("CREATE INDEX IF NOT EXISTS ix_perf ON perf_items(report, kind, measure, code)")
    con.commit()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
