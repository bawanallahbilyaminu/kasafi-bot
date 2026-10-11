"""Project-level spending from the quarterly Budget Implementation Reports.

Only two tables in each report are per project: "Primary Healthcare Capital Expenditure by Project" and
"Basic Education Capital Expenditure by Project". Every other ministry's spending is published per ministry/agency
only, so for their projects the latest per-project figure stays the 2026 budget's Jan-Sep 2025 column.

Output table `perf_projects`: report, mda_code, mda_name, project, budget_original, budget_final, quarter_actual,
ytd_actual, ytd_pct, balance, source_page, source_file.

Check: per report and agency, the sum of project YTD spending is compared with the agency's capital YTD in
perf_items (printed; a mismatch means a row was missed or mis-read).

Usage: python -I pipeline/parse_report_projects.py <db.sqlite> <report.pdf> [...]
"""
import re
import sqlite3
import subprocess
import sys

TITLE_RE = re.compile(r"Budget Performance Report (20\d\d) Q([1-4]) - (.+?)\s*$")
START_RE = re.compile(r"^\s*(0\d{11}) - ")
NUM = r"-?\d{1,3}(?:,\d{3})*\.\d{2}"
TOKEN_RE = re.compile(rf"(?<!\S)(?:{NUM}%?|-?\d+(?:\.\d+)?%|-)(?!\S)")
GLUED = re.compile(rf"(?<=[A-Za-z)\]])({NUM})")       # "sanitary pads360,278,560.69" -> "sanitary pads 360,278,560.69"


def num(t):
    return 0.0 if t == "-" else float(t.rstrip("%").replace(",", ""))


def records(text):
    """Yield (report, page, col, lines) per project row of the 'by Project' tables."""
    report, in_table, col, cur = None, False, 52, None
    for pno, page in enumerate(text.split("\f"), 1):
        for line in page.splitlines():
            m = TITLE_RE.search(line)
            if m:
                if cur:
                    yield cur
                    cur = None
                report = f"{m.group(1)}Q{m.group(2)}"
                in_table = m.group(3).strip().endswith("by Project")
                continue
            if not in_table:
                continue
            if "Project Description" in line:
                col = line.index("Project Description")
                continue
            if re.match(r"^\s*\d\.[A-Z]\s|^\s*Table \d+:", line):     # next section heading
                if cur:
                    yield cur
                    cur = None
                in_table = False
                continue
            if START_RE.match(line):
                if cur:
                    yield cur
                cur = (report, pno, col, [line])
            elif cur and line.strip():
                cur[3].append(line)
    if cur:
        yield cur


def parse(pdf, names=None):
    """names: {code: agency name} (from perf_items) to separate the agency column from the project description."""
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
    rows = []
    for report, pno, _col, lines in records(text):
        code = START_RE.match(lines[0]).group(1)
        whole = " ".join(GLUED.sub(r" \1", ln.strip()) for ln in lines)
        whole = whole.split(" - ", 1)[1] if " - " in whole else whole
        whole = re.sub(r"Page \| \d+.*$", "", whole)
        toks = list(TOKEN_RE.finditer(whole))
        pct_i = next((i for i, t in enumerate(toks) if t.group().endswith("%")), None)
        if pct_i is None or pct_i < 4:
            continue
        orig, final, q, ytd = (num(t.group()) for t in toks[pct_i - 4:pct_i])
        after = [t.group() for t in toks[pct_i + 1:]]
        bal = num(after[0]) if after else None
        desc = re.sub(r"\s+", " ", TOKEN_RE.sub(" ", whole)).strip()
        desc = re.sub(r"(\s\d){1,2}\s*$", "", desc)                  # HOPE-GOV tagging columns ("1 0")
        agency = (names or {}).get(code) or ""
        base = re.sub(r"\s*\(.*?\)\s*", " ", agency).strip()
        if base and desc.lower().startswith(base.lower()):
            desc = desc[len(base):].strip()
        for acr in re.findall(r"\(.*?\)", agency):
            desc = desc.replace(acr, " ", 1)
        desc = re.sub(r"\s{2,}", " ", desc).strip()
        rows.append({"report": report, "mda_code": code, "mda_name": agency, "project": desc,
                     "budget_original": orig, "budget_final": final, "quarter_actual": q, "ytd_actual": ytd,
                     "ytd_pct": num(toks[pct_i].group()), "balance": bal, "source_page": pno,
                     "source_file": pdf.split("/")[-1]})
    return rows


def main(db, pdfs):
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS perf_projects (
        id INTEGER PRIMARY KEY, report TEXT, mda_code TEXT, mda_name TEXT, project TEXT, budget_original REAL,
        budget_final REAL, quarter_actual REAL, ytd_actual REAL, ytd_pct REAL, balance REAL, source_page INTEGER,
        source_file TEXT)""")
    names = dict(con.execute("SELECT code, name FROM perf_items WHERE kind='exp_admin' AND measure='total' GROUP BY code"))
    for pdf in pdfs:
        rows = parse(pdf, names)
        for rep in {r["report"] for r in rows}:
            con.execute("DELETE FROM perf_projects WHERE report=?", (rep,))
        # PHC / basic education projects are printed twice in some reports (all-projects table + their own table)
        seen, uniq = set(), []
        for r in rows:
            k = (r["report"], r["mda_code"], r["project"][:60], r["budget_final"], r["ytd_actual"])
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        rows = uniq
        for r in rows:
            con.execute(f"INSERT INTO perf_projects ({', '.join(r)}) VALUES ({', '.join('?' for _ in r)})", list(r.values()))
        con.commit()
        print(f"{pdf.split('/')[-1]}: {len(rows)} project rows")
        for rep, code, n, s in con.execute("SELECT report, mda_code, count(*), sum(ytd_actual) FROM perf_projects "
                                           "WHERE source_file=? GROUP BY report, mda_code", (pdf.split("/")[-1],)):
            ag = con.execute("SELECT ytd_actual FROM perf_items WHERE report=? AND kind='exp_admin' AND measure='capital' "
                             "AND code=?", (rep, code)).fetchone()
            ok = ag is not None and abs((ag[0] or 0) - s) < 1
            print(f"  {rep} {code}: {n} projects, YTD {s:,.2f} vs agency capital {ag[0] if ag else None:,.2f} "
                  f"{'OK' if ok else 'MISMATCH'}" if ag else f"  {rep} {code}: {n} projects, YTD {s:,.2f} (no agency row)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_perf_proj ON perf_projects(report, mda_code)")
    con.commit()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
