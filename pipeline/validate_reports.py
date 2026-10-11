"""Validate quarterly implementation report data (perf_items) inside each report and against the 2026 budget.

Usage: python -I validate_reports.py <db.sqlite> [report ...]   (default: 2025Q2 2025Q3 2025Q4 2026Q2)
"""
import sqlite3
import sys

TOL = 1.0
COLS = ["budget_original", "budget_revised", "quarter_actual", "ytd_actual"]


def main(db, reports):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    checks = fails = 0

    def check(label, a, b):
        nonlocal checks, fails
        checks += 1
        if a is None or b is None or abs(a - b) > TOL:
            fails += 1
            if fails <= 40:
                print(f"FAIL {label}: {a} vs {b}")

    for rep in reports:
        rows = lambda kind, measure: con.execute("SELECT * FROM perf_items WHERE report=? AND kind=? AND measure=?",
                                                 (rep, kind, measure)).fetchall()
        # 1. admin hierarchy for every measure
        for measure in ("total", "personnel", "overhead", "other", "capital"):
            rs = rows("exp_admin", measure)
            if not rs:
                continue
            total = next((r for r in rs if r["code"] == ""), None)
            sectors = [r for r in rs if len(r["code"]) == 12 and r["code"][2:] == "0" * 10]
            ministries = [r for r in rs if len(r["code"]) == 12 and r["code"][4:] == "0" * 8 and r["code"][2:] != "0" * 10]
            mdas = [r for r in rs if len(r["code"]) == 12 and r["code"][4:] != "0" * 8]
            for c in COLS:
                if total:
                    check(f"{rep} {measure} sectors->total {c}", sum(r[c] for r in sectors), total[c])
                for s in sectors:
                    check(f"{rep} {measure} ministries->{s['name']} {c}",
                          sum(r[c] for r in ministries if r["code"][:2] == s["code"][:2]), s[c])
                for m in ministries:
                    check(f"{rep} {measure} mdas->{m['name']} {c}",
                          sum(r[c] for r in mdas if r["code"][:4] == m["code"][:4]), m[c])
        # 2. personnel + overhead + other + capital = total, per admin code (YTD and revised budget)
        parts = {}
        for measure in ("personnel", "overhead", "other", "capital"):
            for r in rows("exp_admin", measure):
                d = parts.setdefault(r["code"], {c: 0.0 for c in COLS})
                for c in COLS:
                    d[c] += r[c]
        for r in rows("exp_admin", "total"):
            for c in ("budget_revised", "ytd_actual"):
                check(f"{rep} parts->total {r['code']} {r['name']} {c}", parts.get(r["code"], {}).get(c, 0.0), r[c])
        # 3. functional / programme totals equal the admin total
        adm = next((r for r in rows("exp_admin", "total") if r["code"] == ""), None)
        for kind in ("exp_function", "exp_programme", "exp_economic"):
            t = next((r for r in rows(kind, "total") if r["code"] == ""), None)
            if t and adm:
                for c in ("budget_revised", "ytd_actual"):
                    check(f"{rep} {kind} total == admin total {c}", t[c], adm[c])

    # 4. cross-document: 2025 Q3 report YTD == "2025 Jan-Sep performance" printed in the 2026 budget (grand totals;
    #    the budget's overhead+debt service == the report's overhead+other). Ministry-level differences are
    #    reclassifications made when the 2026 budget re-filed 2025 figures; they are counted, not failed.
    b = {r["measure"]: r for r in con.execute("SELECT * FROM line_items WHERE kind='exp_admin' AND code=''")}
    p = {r["measure"]: r for r in con.execute("SELECT * FROM perf_items WHERE report='2025Q3' AND kind='exp_admin' AND code=''")}
    if b and p:
        for m in ("total", "personnel", "capital"):
            check(f"2026 budget vs 2025Q3 report {m} spent", b[m]["perf_2025_jan_sep"], p[m]["ytd_actual"])
            check(f"2026 budget vs 2025Q3 report {m} revised", b[m]["revised_2025"], p[m]["budget_revised"])
        check("2026 budget overhead+debt vs 2025Q3 overhead+other spent",
              b["overhead"]["perf_2025_jan_sep"] + b["debt_service"]["perf_2025_jan_sep"],
              p["overhead"]["ytd_actual"] + p["other"]["ytd_actual"])
        recl = con.execute("SELECT count(*) FROM line_items b JOIN perf_items r ON r.code=b.code AND r.report='2025Q3' "
                           "AND r.kind='exp_admin' AND r.measure='total' WHERE b.kind='exp_admin' AND b.measure='total' "
                           "AND abs(b.perf_2025_jan_sep - r.ytd_actual) > 1").fetchone()[0]
        print(f"info: {recl} MDA totals differ between the 2026 budget's 2025 column and the 2025 Q3 report (reclassified)")

    print(f"\n{checks - fails}/{checks} checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(args[0], args[1:] or ["2025Q2", "2025Q3", "2025Q4", "2026Q2"]))
