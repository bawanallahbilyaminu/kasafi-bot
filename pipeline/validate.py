"""Check the extracted budget database against the totals printed in the document.

Usage: python -I validate.py <db.sqlite>                                   (2026 budget)
       python -I validate.py <db.sqlite> --year 2025 --table line_items_2025 --projects projects_2025
Exit code 1 if any check fails.
"""
import sqlite3
import sys
from collections import defaultdict

COLS = ["actual_2024", "revised_2025", "perf_2025_jan_sep", "approved_2026", "estimate_2027", "estimate_2028"]
TOL = 1.0  # naira

# Printed on the Summary page (page 1)
SUMMARY = {
    ("exp_admin", "total"): [67527761629.59, 526882142484.39, 227654787906.93, 758700526537.89, 667268894218.69, 660110770000.60],
    ("exp_admin", "personnel"): [15759333245.71, 61211091739.44, 50786894985.15, 70571647882.76, 69790867882.76, 74994507882.76],
    ("exp_admin", "overhead"): [14935223021.63, 87195457352.31, 44022371403.48, 115022286551.67, 152415664596.43, 152739673650.86],
    ("exp_admin", "debt_service"): [10872910059.66, 23969363038.39, 11958725449.04, 19763000000.00, 18363000000.00, 18363000000.00],
    ("exp_admin", "capital"): [25960295302.59, 354506230354.25, 120886796069.26, 553343592103.46, 426699361739.50, 414013588466.98],
}

fails = 0
checks = 0
known = 0
# Discrepancies that exist in the source documents themselves (verified by hand), not extraction errors
KNOWN_SOURCE_DIFFS = {
    # 2025 budget: Water Board capital 2024 Jan-Sep performance is printed as 671,280,010.00 but its project
    # lines sum to 671,280,000.00 (a N10 difference inside the document); the grand total inherits it.
    ("projects total perf_2024_jan_sep", 10.0),
    ("projects by MDA Water Board perf_2024_jan_sep", 10.0),
}


def check(label, a, b):
    global fails, checks, known
    checks += 1
    if a is not None and b is not None and any(label == k and abs(abs(a - b) - d) < 0.01 for k, d in KNOWN_SOURCE_DIFFS):
        known += 1
        return
    if a is None or b is None or abs(a - b) > TOL:
        fails += 1
        print(f"FAIL {label}: {a} vs {b}")


def main(db, year=2026, table="line_items", ptable="projects"):
    global COLS
    y = year
    COLS = [f"actual_{y-2}", f"revised_{y-1}", f"perf_{y-1}_jan_sep", f"approved_{y}", f"estimate_{y+1}", f"estimate_{y+2}"]
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    if year != 2026:  # take the document's own grand totals as the reference
        for m in ("total", "personnel", "overhead", "debt_service", "capital"):
            t = con.execute(f"SELECT * FROM {table} WHERE kind='exp_admin' AND measure=? AND code=''", (m,)).fetchone()
            if t:
                SUMMARY[("exp_admin", m)] = [t[c] or 0 for c in COLS]

    def rows(kind, measure):
        return con.execute(f"SELECT * FROM {table} WHERE kind=? AND measure=? ORDER BY id", (kind, measure)).fetchall()

    # 1. Grand totals vs summary page
    for (kind, measure), vals in SUMMARY.items():
        tot = [r for r in rows(kind, measure) if r["code"] == ""]
        for i, c in enumerate(COLS):
            check(f"summary {kind}/{measure}/{c}", tot[0][c] if tot else None, vals[i])

    # 2. Admin hierarchy: MDAs -> ministry -> sector -> total, for every admin table
    admin_kinds = con.execute(f"SELECT DISTINCT kind, measure FROM {table} WHERE kind IN "
                              "('exp_admin','revenue_admin','basic_edu_admin','phc_admin')").fetchall()
    for kind, measure in admin_kinds:
        rs = rows(kind, measure)
        total = next((r for r in rs if r["code"] == ""), None)
        sectors = [r for r in rs if len(r["code"]) == 12 and r["code"][2:] == "0" * 10]
        ministries = [r for r in rs if len(r["code"]) == 12 and r["code"][4:] == "0" * 8 and r["code"][2:] != "0" * 10]
        mdas = [r for r in rs if len(r["code"]) == 12 and r["code"][4:] != "0" * 8]
        for c in COLS:
            if total:
                check(f"{kind}/{measure} sectors->total {c}", sum(r[c] or 0 for r in sectors), total[c])
            for s in sectors:
                check(f"{kind}/{measure} ministries->{s['name']} {c}",
                      sum(r[c] or 0 for r in ministries if r["code"][:2] == s["code"][:2]), s[c])
            for m in ministries:
                check(f"{kind}/{measure} mdas->{m['name']} {c}",
                      sum(r[c] or 0 for r in mdas if r["code"][:4] == m["code"][:4]), m[c])

    # 3. Total = personnel + overhead + debt + capital, per admin code
    parts = defaultdict(lambda: defaultdict(float))
    totals = {}
    for r in con.execute(f"SELECT * FROM {table} WHERE kind='exp_admin'"):
        if r["measure"] == "total":
            totals[r["code"]] = r
        else:
            for c in COLS:
                parts[r["code"]][c] += r[c] or 0
    for code, t in totals.items():
        for c in COLS:
            check(f"exp_admin parts->total {code} {t['name']} {c}", parts[code][c], t[c])

    # 4. Other classifications sum to the same grand total
    for kind in ("exp_function", "exp_location", "exp_programme"):
        for measure in ("total", "capital", "personnel", "overhead"):
            rs = rows(kind, measure)
            tot = next((r for r in rs if r["code"] == ""), None)
            if not tot and kind == "exp_location":  # location table's total row is "333 Sokoto"
                tot = next((r for r in rs if r["code"] == "333"), None)
                rs = [r for r in rs if r["code"] != "333"]
            if not tot:
                print(f"WARN no total row for {kind}/{measure}")
                continue
            lens = sorted({len(r["code"]) for r in rs if r["code"]})
            top = [r for r in rs if r["code"] and len(r["code"]) == lens[0]]
            for c in COLS:
                check(f"{kind}/{measure} top-level->total {c}", sum(r[c] or 0 for r in top), tot[c])
                check(f"{kind}/{measure} total == exp_admin {c}", tot[c], SUMMARY[("exp_admin", measure)][COLS.index(c)])

    # 5. Projects reconcile with capital by MDA
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (ptable,)).fetchone():
        print(f"(no {ptable} table yet: project checks skipped)")
        print(f"\n{checks - fails}/{checks} checks passed")
        return 1 if fails else 0
    for c in COLS:
        p = con.execute(f"SELECT sum(coalesce({c},0)) FROM {ptable}").fetchone()[0]
        check(f"projects total {c}", p, SUMMARY[("exp_admin", "capital")][COLS.index(c)])
    q = ("SELECT a.code, a.name, a.{c} AS v, (SELECT sum(coalesce({c},0)) FROM " + ptable + " p WHERE p.mda_code=a.code) AS s "
         "FROM " + table + " a WHERE a.kind='exp_admin' AND a.measure='capital' AND length(a.code)=12 AND substr(a.code,5)!='00000000'")
    for c in COLS:
        for r in con.execute(q.format(c=c)):
            check(f"projects by MDA {r['name']} {c}", r["s"] or 0, r["v"])

    # 6. MDA economic detail: top line '2' EXPENDITURES equals the MDA total
    for r in con.execute(f"SELECT d.mda_code, d.mda_name, d.{COLS[3]} AS v, a.{COLS[3]} AS t FROM {table} d "
                         f"JOIN {table} a ON a.code=d.mda_code AND a.kind='exp_admin' AND a.measure='total' "
                         "WHERE d.kind='mda_exp_economic' AND d.code='2'"):
        check(f"mda detail total {r['mda_name']}", r["v"], r["t"])

    print(f"\n{checks - fails}/{checks} checks passed" + (f" ({known} known source-document discrepancies, see KNOWN_SOURCE_DIFFS)" if known else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--table", default="line_items")
    ap.add_argument("--projects", default="projects")
    a = ap.parse_args()
    sys.exit(main(a.db, a.year, a.table, a.projects))
