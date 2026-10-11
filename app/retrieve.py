"""Turn a parsed question into grounded facts from the budget database.

Every fact carries the exact figure, the year/measure it refers to, and the source page,
so the answer writer (N-ATLaS) can only restate what is in the document.
"""
import re
import sqlite3
from dataclasses import dataclass, field

from .fmt import naira, pct, pct_str

YEAR_COL = {2024: "actual_2024", 2025: "revised_2025", 2026: "approved_2026", 2027: "estimate_2027", 2028: "estimate_2028"}
MEASURE_HA = {"total": "jimillar kasafi", "personnel": "albashi (personnel)", "overhead": "kudaden gudanarwa (overhead)",
              "capital": "manyan ayyuka (capital)", "debt_service": "biyan bashi (debt service)"}
MEASURE_EN = {"total": "total budget", "personnel": "personnel (salaries)", "overhead": "overhead (running costs)",
              "capital": "capital projects", "debt_service": "debt service"}
YEAR_LABEL_HA = {2024: "abin da aka kashe a 2024", 2025: "kasafin 2025 (wanda aka sabunta)",
                 2026: "kasafin 2026 da aka amince", 2027: "hasashen 2027", 2028: "hasashen 2028"}
YEAR_LABEL_EN = {2024: "2024 actual spending", 2025: "2025 revised budget", 2026: "2026 approved budget",
                 2027: "2027 estimate", 2028: "2028 estimate"}


FUNC_HA = {"701": "Ayyukan gwamnati na gaba daya", "703": "Tsaro da oda", "704": "Harkokin tattalin arziki",
           "705": "Kare muhalli", "706": "Gidaje da ababen more rayuwa", "707": "Lafiya",
           "708": "Wasanni, al'adu da addini", "709": "Ilimi", "710": "Kariyar zamantakewa",
           "7101": "Tallafi ga masu nakasa", "7102": "Fansho da tsofaffi", "7104": "Iyali da yara",
           "7105": "Rashin aikin yi"}
CAT_HA = {"7101": "Nakasa da rashin lafiya", "7102": "Fansho da tsofaffi", "7103": "Iyalan mamata",
          "7104": "Iyali da yara", "7105": "Rashin aikin yi", "7106": "Gidaje", "7107": "Marasa galihu",
          "7109": "Sauran kariyar zamantakewa"}
SECTOR_HA = {"Administration Sector": "gudanarwa", "Economic Sector": "tattalin arziki", "Law and Justice": "shari'a",
             "Social Sector": "walwalar jama'a (ilimi, lafiya da sauransu)"}


@dataclass
class Fact:
    key: str
    value: float
    label_ha: str
    label_en: str
    page: int
    is_pct: bool = False
    is_count: bool = False

    def text(self, lang):
        if self.is_count:
            v = f"{int(self.value):,}"
        else:
            v = pct_str(self.value, lang) if self.is_pct else naira(self.value, lang)
        return f"{self.label_ha if lang == 'ha' else self.label_en}: {v}"


@dataclass
class Retrieval:
    intent: str
    subject_ha: str = ""
    subject_en: str = ""
    facts: list = field(default_factory=list)
    items: list = field(default_factory=list)  # e.g. projects: dicts with name, amount, lga, page
    pages: set = field(default_factory=set)
    note: str = ""

    def add(self, f):
        self.facts.append(f)
        if f.page:
            self.pages.add(f.page)


class BudgetStore:
    def __init__(self, path):
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row

    def admin_row(self, code, measure="total"):
        return self.con.execute("SELECT * FROM line_items WHERE kind='exp_admin' AND measure=? AND code=?",
                                (measure, code)).fetchone()

    def name_of(self, code):
        r = self.admin_row(code)
        return r["name"] if r else code

    # ------------------------------------------------------------------ intents
    def overview(self, p):
        r = Retrieval("overview", "Kasafin Kudin Jihar Sokoto 2026", "Sokoto State 2026 budget")
        tot = self.con.execute("SELECT * FROM line_items WHERE kind='exp_admin' AND measure='total' AND code=''").fetchone()
        r.add(Fact("total_2026", tot["approved_2026"], "Jimillar kasafin 2026", "Total 2026 budget", tot["source_page"]))
        for m in ("personnel", "overhead", "debt_service", "capital"):
            row = self.con.execute("SELECT * FROM line_items WHERE kind='exp_admin' AND measure=? AND code=''", (m,)).fetchone()
            r.add(Fact(f"{m}_2026", row["approved_2026"], MEASURE_HA[m].capitalize(), MEASURE_EN[m].capitalize(), row["source_page"]))
        r.add(Fact("total_2025", tot["revised_2025"], "Kasafin 2025 (wanda aka sabunta)", "2025 revised budget", tot["source_page"]))
        r.add(Fact("spent_2025", tot["perf_2025_jan_sep"], "Abin da aka kashe Janairu-Satumba 2025",
                   "Spent Jan-Sep 2025", tot["source_page"]))
        r.add(Fact("perf_2025", pct(tot["perf_2025_jan_sep"], tot["revised_2025"]), "Kaso da aka aiwatar (Jan-Sat 2025)",
                   "2025 implementation rate (Jan-Sep)", tot["source_page"], is_pct=True))
        sectors = self.con.execute("SELECT * FROM line_items WHERE kind='exp_admin' AND measure='total' AND length(code)=12 "
                                   "AND substr(code,3)='0000000000' ORDER BY approved_2026 DESC").fetchall()
        for s in sectors:
            ha = SECTOR_HA.get(s["name"], s["name"])
            r.add(Fact(f"sector_{s['code']}", s["approved_2026"], f"Bangaren {ha}", s["name"], s["source_page"]))
        return r

    def mda(self, p, code):
        name = self.name_of(code)
        r = Retrieval("mda", name, name)
        tot = self.admin_row(code, "total")
        if not tot:
            return r
        years = [y for y in p.years if y in YEAR_COL] or [2026]
        if (p.performance or 2025 in years) and years != [2025]:
            pass
        perf_block = p.performance or 2025 in years
        if perf_block:
            years = [y for y in years if y != 2025] or ([2026] if not p.performance and 2025 not in p.years else [])
        measures = [p.measure] if p.measure in ("personnel", "overhead", "capital", "debt_service") else ["total"]
        for m in measures:
            row = self.admin_row(code, m)
            if not row:
                continue
            for y in years:
                r.add(Fact(f"{m}_{y}", row[YEAR_COL[y]], f"{MEASURE_HA[m].capitalize()} — {YEAR_LABEL_HA[y]}",
                           f"{MEASURE_EN[m].capitalize()} — {YEAR_LABEL_EN[y]}", row["source_page"]))
        if measures == ["total"] and 2026 in years:
            for m in ("personnel", "overhead", "debt_service", "capital"):
                row = self.admin_row(code, m)
                if row and row["approved_2026"]:
                    r.add(Fact(f"{m}_2026", row["approved_2026"], f"{MEASURE_HA[m].capitalize()} (2026)",
                               f"{MEASURE_EN[m].capitalize()} (2026)", row["source_page"]))
        # performance: 2025 revised vs actual Jan-Sep, for the asked measure (default total + capital)
        if perf_block:
            for m in (measures if measures != ["total"] else ["total", "capital"]):
                row = self.admin_row(code, m)
                if row and row["revised_2025"]:
                    r.add(Fact(f"{m}_rev2025", row["revised_2025"], f"{MEASURE_HA[m].capitalize()} — kasafin 2025",
                               f"{MEASURE_EN[m].capitalize()} — 2025 revised budget", row["source_page"]))
                    r.add(Fact(f"{m}_spent2025", row["perf_2025_jan_sep"],
                               f"{MEASURE_HA[m].capitalize()} — abin da aka kashe Jan-Sat 2025",
                               f"{MEASURE_EN[m].capitalize()} — spent Jan-Sep 2025", row["source_page"]))
                    r.add(Fact(f"{m}_pct2025", pct(row["perf_2025_jan_sep"], row["revised_2025"]),
                               f"{MEASURE_HA[m].capitalize()} — kaso da aka aiwatar",
                               f"{MEASURE_EN[m].capitalize()} — implementation rate", row["source_page"], is_pct=True))
        if p.compare and tot["revised_2025"]:
            ch = pct(tot["approved_2026"] - tot["revised_2025"], tot["revised_2025"])
            if not any(f.key == "total_rev2025" for f in r.facts):
                r.add(Fact("rev2025_cmp", tot["revised_2025"], "Kasafin 2025 (wanda aka sabunta)", "2025 revised budget", tot["source_page"]))
            if not any(f.key == "total_2026" for f in r.facts):
                r.add(Fact("app2026_cmp", tot["approved_2026"], "Kasafin 2026", "2026 approved budget", tot["source_page"]))
            r.add(Fact("chg_pct", abs(ch), "Karuwa daga 2025 zuwa 2026" if ch >= 0 else "Raguwa daga 2025 zuwa 2026",
                       "Increase from 2025 to 2026" if ch >= 0 else "Decrease from 2025 to 2026", tot["source_page"], is_pct=True))
        # for a ministry-level code, list its biggest agencies; for capital questions, top projects
        if code[4:] == "00000000":
            kids = self.con.execute("SELECT * FROM line_items WHERE kind='exp_admin' AND measure='total' AND length(code)=12 "
                                    "AND substr(code,1,4)=? AND code!=? AND approved_2026>0 ORDER BY approved_2026 DESC LIMIT 4",
                                    (code[:4], code)).fetchall()
            if len(kids) > 1:
                for k in kids:
                    r.items.append({"type": "agency", "name": k["name"], "amount": k["approved_2026"], "page": k["source_page"]})
        if p.measure == "capital" or p.project_terms or p.wants_projects:
            like = code[:4] + "%" if code[4:] == "00000000" else code
            r.items += self.projects(p, mda_like=like, limit=4)
        return r

    def function(self, p, code):
        row = self.con.execute("SELECT * FROM line_items WHERE kind='exp_function' AND measure='total' AND code=?",
                               (code,)).fetchone()
        name_en = row["name"].title() if row else code
        r = Retrieval("function", f"{FUNC_HA.get(code, name_en)} ({name_en})", f"{name_en} (all ministries and agencies)")
        if not row:
            return r
        years = [y for y in p.years if y in YEAR_COL] or [2026]
        perf_block = p.performance or 2025 in years
        if perf_block:
            years = [y for y in years if y != 2025]
        for y in years:
            r.add(Fact(f"func_{y}", row[YEAR_COL[y]], f"Jimillar kasafi — {YEAR_LABEL_HA[y]}",
                       f"Total — {YEAR_LABEL_EN[y]}", row["source_page"]))
        if 2026 in years:
            for m in ("personnel", "overhead", "capital"):
                mr = self.con.execute("SELECT * FROM line_items WHERE kind='exp_function' AND measure=? AND code=?",
                                      (m, code)).fetchone()
                if mr and mr["approved_2026"]:
                    r.add(Fact(f"{m}_2026", mr["approved_2026"], f"{MEASURE_HA[m].capitalize()} (2026)",
                               f"{MEASURE_EN[m].capitalize()} (2026)", mr["source_page"]))
        if row["revised_2025"]:
            r.add(Fact("func_rev2025", row["revised_2025"], "Kasafin 2025", "2025 revised budget", row["source_page"]))
            r.add(Fact("func_spent2025", row["perf_2025_jan_sep"], "Abin da aka kashe Jan-Sat 2025",
                       "Spent Jan-Sep 2025", row["source_page"]))
            r.add(Fact("func_pct2025", pct(row["perf_2025_jan_sep"], row["revised_2025"]), "Kaso da aka aiwatar (2025)",
                       "2025 implementation rate", row["source_page"], is_pct=True))
        # sub-categories (e.g. old age / pensions, disability, unemployment under social protection)
        if len(code) == 3:
            subs = self.con.execute("SELECT * FROM line_items WHERE kind='exp_function' AND measure='total' AND length(code)=4 "
                                    "AND code LIKE ? AND approved_2026>0 ORDER BY approved_2026 DESC LIMIT 5", (code + "%",)).fetchall()
            for sb in subs:
                if re.fullmatch(r"[A-Z ,&.()'-]+", sb["name"] or ""):
                    en = sb["name"].title().replace("N.E.C.", "(other)").replace("N.E.C", "(other)").replace("Exclussion", "Exclusion")
                    ha = CAT_HA.get(sb["code"])
                    r.items.append({"type": "category", "name": f"{ha} ({en})" if ha else en, "name_en": en,
                                    "amount": sb["approved_2026"], "page": sb["source_page"]})
        r.items += self.projects(p, function_like=code + "%", limit=4)
        return r

    # ------------------------------------------------------------------ analysis
    def _scope(self, p):
        where, args, ha, en = [], [], [], []
        if p.mda_codes:
            c = p.mda_codes[0]
            if c[4:] == "0" * 8:
                where.append("mda_code LIKE ?"); args.append(c[:4] + "%")
            else:
                where.append("mda_code = ?"); args.append(c)
            n = self.name_of(c); ha.append(n); en.append(n)
        elif p.function_codes:
            fc = p.function_codes[0]
            where.append("function_code LIKE ?"); args.append(fc + "%")
            row = self.con.execute("SELECT name FROM line_items WHERE kind='exp_function' AND measure='total' AND code=?",
                                   (fc,)).fetchone()
            n = row[0].title() if row else fc
            ha.append(FUNC_HA.get(fc, n)); en.append(n)
        if p.lga_codes:
            where.append("location_code = ?"); args.append(p.lga_codes[0])
            nm = self.con.execute("SELECT location_name FROM projects WHERE location_code=? LIMIT 1", (p.lga_codes[0],)).fetchone()
            nm = nm[0].title() if nm else p.lga_codes[0]
            ha.append(f"Karamar Hukumar {nm}"); en.append(f"{nm} LGA")
        return (" AND ".join(where) or "1=1"), args, (" — ".join(ha) or "Duk jiha"), (" — ".join(en) or "Whole state")

    def project_status(self, p):
        where, args, sha, sen = self._scope(p)
        r = Retrieval("project_status", f"Matsayin ayyuka: {sha}", f"Project status: {sen}")
        pg = self.con.execute(f"SELECT min(source_page) FROM projects WHERE {where}", args).fetchone()[0] or 49
        one = lambda sql: self.con.execute(f"SELECT count(*), coalesce(sum(revised_2025),0), coalesce(sum(perf_2025_jan_sep),0), "
                                           f"coalesce(sum(approved_2026),0) FROM projects WHERE {where} AND {sql}", args).fetchone()
        allp = one("approved_2026 > 0")
        cont = one("revised_2025 > 0 AND approved_2026 > 0")
        started = one("perf_2025_jan_sep > 0 AND revised_2025 > 0 AND approved_2026 > 0")
        idle = one("revised_2025 > 0 AND coalesce(perf_2025_jan_sep,0) = 0 AND approved_2026 > 0")
        new = one("coalesce(revised_2025,0) = 0 AND approved_2026 > 0")
        gone = one("revised_2025 > 0 AND coalesce(approved_2026,0) = 0")
        F = lambda k, v, ha, en, **kw: r.add(Fact(k, v, ha, en, pg, **kw))
        F("n_all", allp[0], "Ayyukan da ke cikin kasafin 2026", "Projects in the 2026 budget", is_count=True)
        F("n_cont", cont[0], "Ayyukan da aka tsara a 2025 kuma suka ci gaba a 2026", "Projects budgeted in 2025 and continuing in 2026", is_count=True)
        F("amt_cont", cont[3], "Kudin da aka ware wa wadannan ayyuka a 2026", "2026 allocation for these continuing projects")
        F("n_started", started[0], "Daga cikinsu, wadanda aka fara kashe musu kudi a 2025 (Jan-Sat) kuma ba a kammala ba", "Of these, work started in 2025 (money spent Jan-Sep) and still continuing", is_count=True)
        F("amt_started_spent", started[2], "Abin da aka kashe musu a 2025 (Jan-Sat)", "Spent on them in 2025 (Jan-Sep)")
        F("n_idle", idle[0], "Wadanda aka ware musu kudi a 2025 amma ba a kashe ko sisi ba (Jan-Sat), aka sake sanya su a 2026", "Budgeted in 2025 but nothing spent (Jan-Sep), budgeted again in 2026", is_count=True)
        F("amt_idle25", idle[1], "Kudin da aka ware musu a 2025 ba tare da an kashe ba", "Their 2025 budget, unspent")
        F("n_new", new[0], "Sababbin ayyuka a 2026 (babu su a 2025)", "New projects in 2026 (not in the 2025 budget)", is_count=True)
        F("amt_new", new[3], "Kudin sababbin ayyuka a 2026", "2026 allocation for new projects")
        F("n_gone", gone[0], "Ayyukan 2025 da ba su cikin kasafin 2026 (an kammala ko an daina)", "2025 projects not in the 2026 budget (completed or dropped)", is_count=True)
        ex = self.con.execute(f"SELECT * FROM projects WHERE {where} AND perf_2025_jan_sep > 0 AND revised_2025 > 0 AND approved_2026 > 0 "
                              "ORDER BY approved_2026 DESC LIMIT 3", args).fetchall()
        for x in ex:
            r.items.append(self._proj_item(x, "An fara a 2025, ana ci gaba a 2026:", "Started in 2025, continuing in 2026:"))
        ex = self.con.execute(f"SELECT * FROM projects WHERE {where} AND revised_2025 > 0 AND coalesce(perf_2025_jan_sep,0) = 0 AND approved_2026 > 0 "
                              "ORDER BY revised_2025 DESC LIMIT 3", args).fetchall()
        for x in ex:
            r.items.append(self._proj_item(x, "An ware kudi a 2025 amma ba a kashe ba:", "Budgeted in 2025 but nothing spent:"))
        r.note = "jan_sep"
        return r

    def _proj_item(self, x, gha, gen):
        return {"type": "status_project", "name": x["project"], "amount": x["approved_2026"], "budget_2025": x["revised_2025"],
                "spent_2025": x["perf_2025_jan_sep"], "lga": x["location_name"], "page": x["source_page"],
                "group_ha": gha, "group_en": gen}

    def ranking(self, p):
        order = "ASC" if p.rank_order == "bottom" else "DESC"
        top_ha = "mafi karanci" if order == "ASC" else "mafi yawa"
        top_en = "lowest" if order == "ASC" else "highest"
        if p.rank_unit == "lga":
            rows = self.con.execute(f"SELECT name, approved_2026 v, source_page FROM line_items WHERE kind='exp_location' AND "
                                    f"measure='total' AND length(code)=8 AND code!='33342400' ORDER BY approved_2026 {order} LIMIT 5").fetchall()
            r = Retrieval("ranking", f"Kananan hukumomi da suka fi samun kudi kai tsaye a 2026 ({top_ha})",
                          f"LGAs by budget located there in 2026 ({top_en})")
            for i, x in enumerate(rows, 1):
                r.add(Fact(f"rank{i}", x["v"], f"{i}. {x['name'].title()}", f"{i}. {x['name'].title()}", x["source_page"]))
            r.note = "statewide"
            return r
        if p.rank_unit == "project":
            where, args, sha, sen = self._scope(p)
            rows = self.con.execute(f"SELECT * FROM projects WHERE {where} AND approved_2026 > 0 ORDER BY approved_2026 {order} LIMIT 5",
                                    args).fetchall()
            r = Retrieval("ranking", f"Ayyuka {top_ha} a 2026 — {sha}", f"Projects with the {top_en} 2026 allocation — {sen}")
            r.items = [{"type": "project", "name": x["project"], "amount": x["approved_2026"], "lga": x["location_name"],
                        "page": x["source_page"]} for x in rows]
            return r
        # ministries (aggregate ministry-level codes)
        m = p.rank_metric
        base = ("FROM line_items WHERE kind='exp_admin' AND measure=? AND length(code)=12 AND substr(code,5)='00000000' "
                "AND substr(code,3)!='0000000000'")
        if m == "implementation":
            meas = "capital"
            rows = self.con.execute(f"SELECT name, 100.0*perf_2025_jan_sep/revised_2025 v, revised_2025, source_page {base} "
                                    f"AND revised_2025 >= 1e9 ORDER BY v {order} LIMIT 5", (meas,)).fetchall()
            r = Retrieval("ranking", f"Ma'aikatun da suka fi aiwatar da manyan ayyuka a 2025 ({top_ha})",
                          f"Ministries by 2025 capital implementation, Jan-Sep ({top_en})")
            for i, x in enumerate(rows, 1):
                r.add(Fact(f"rank{i}", round(x["v"], 1), f"{i}. {x['name']}", f"{i}. {x['name']}", x["source_page"], is_pct=True))
            r.note = "jan_sep"
            return r
        if m in ("growth", "decline"):
            o = "DESC" if m == "growth" else "ASC"
            rows = self.con.execute(f"SELECT name, 100.0*(approved_2026-revised_2025)/revised_2025 v, source_page {base} "
                                    f"AND revised_2025 >= 1e9 ORDER BY v {o} LIMIT 5", ("total",)).fetchall()
            r = Retrieval("ranking", "Ma'aikatun da kasafinsu ya fi " + ("karuwa" if m == "growth" else "raguwa") + " daga 2025 zuwa 2026",
                          "Ministries with the largest budget " + ("increase" if m == "growth" else "decrease") + " from 2025 to 2026")
            for i, x in enumerate(rows, 1):
                lab = f"{i}. {x['name']}"
                r.add(Fact(f"rank{i}", round(abs(x["v"]), 1), lab + (" (karuwa)" if x["v"] >= 0 else " (raguwa)"),
                           lab + (" (increase)" if x["v"] >= 0 else " (decrease)"), x["source_page"], is_pct=True))
            return r
        meas = p.measure if p.measure in ("personnel", "overhead", "capital") else "total"
        rows = self.con.execute(f"SELECT name, approved_2026 v, source_page {base} ORDER BY approved_2026 {order} LIMIT 5",
                                (meas,)).fetchall()
        r = Retrieval("ranking", f"Ma'aikatun da suka fi samun kudi a 2026 ({top_ha}) — {MEASURE_HA[meas]}",
                      f"Ministries by 2026 allocation ({top_en}) — {MEASURE_EN[meas]}")
        for i, x in enumerate(rows, 1):
            r.add(Fact(f"rank{i}", x["v"], f"{i}. {x['name']}", f"{i}. {x['name']}", x["source_page"]))
        return r

    def lga(self, p, code):
        r = Retrieval("lga")
        row = self.con.execute("SELECT * FROM line_items WHERE kind='exp_location' AND measure='total' AND code=?", (code,)).fetchone()
        name = row["name"].title() if row else code
        if not row:
            pr = self.con.execute("SELECT location_name FROM projects WHERE location_code=? LIMIT 1", (code,)).fetchone()
            name = pr[0].title() if pr else code
        r.subject_ha = f"Karamar Hukumar {name}"
        r.subject_en = f"{name} LGA"
        if row:
            r.add(Fact("lga_2026", row["approved_2026"], f"Kasafin 2026 da aka ware wa {name} kai tsaye",
                       f"2026 budget located in {name}", row["source_page"]))
            if row["revised_2025"]:
                r.add(Fact("lga_rev2025", row["revised_2025"], "Kasafin 2025", "2025 revised budget", row["source_page"]))
                r.add(Fact("lga_spent2025", row["perf_2025_jan_sep"], "Abin da aka kashe Jan-Sat 2025",
                           "Spent Jan-Sep 2025", row["source_page"]))
        n = self.con.execute("SELECT count(*), sum(approved_2026) FROM projects WHERE location_code=? AND approved_2026>0",
                             (code,)).fetchone()
        if n[0]:
            r.add(Fact("lga_projects_2026", n[1], f"Jimillar ayyuka {n[0]} da aka tsara a {name} (2026)",
                       f"Total of {n[0]} capital projects in {name} (2026)", 0))
        r.items = self.projects(p, location=code, limit=5)
        r.note = "statewide"  # many projects are budgeted 'State Wide' and also benefit the LGA
        return r

    def revenue(self, p):
        r = Retrieval("revenue", "Kudaden shigar jiha 2026", "State revenue 2026")
        for code, ha, en in [("11", "Kason Tarayya (FAAC)", "Federation Account share (FAAC)"),
                             ("12", "Kudaden shiga na cikin gida (IGR)", "Independent revenue (IGR)"),
                             ("13", "Tallafi da gudummawa (Aid & Grants)", "Aid and grants"),
                             ("14", "Kudaden ayyukan raya kasa (CDF receipts)", "Capital development fund receipts")]:
            row = self.con.execute("SELECT * FROM line_items WHERE kind IN ('revenue_economic') AND code=? ORDER BY id LIMIT 1",
                                   (code,)).fetchone()
            if row:
                r.add(Fact(f"rev_{code}_2026", row["approved_2026"], f"{ha} — 2026", f"{en} — 2026", row["source_page"]))
                if row["revised_2025"]:
                    r.add(Fact(f"rev_{code}_2025", row["revised_2025"], f"{ha} — kasafin 2025", f"{en} — 2025 budget", row["source_page"]))
                    r.add(Fact(f"rev_{code}_got2025", row["perf_2025_jan_sep"], f"{ha} — abin da aka samu Jan-Sat 2025",
                               f"{en} — received Jan-Sep 2025", row["source_page"]))
        return r

    def project_search(self, p):
        r = Retrieval("project", "Ayyukan raya kasa", "Capital projects")
        r.items = self.projects(p, limit=6)
        return r

    def projects(self, p, mda_like=None, location=None, limit=5, function_like=None):
        where, args = ["approved_2026 > 0"], []
        if function_like:
            where.append("function_code LIKE ?"); args.append(function_like)
        if mda_like:
            where.append("mda_code LIKE ?"); args.append(mda_like)
        if location:
            where.append("location_code = ?"); args.append(location)
        terms = [t for t in p.project_terms]
        if terms:
            q = "project : (" + " OR ".join(f'"{t}"' for t in terms) + ")"
            sql = ("SELECT p.* FROM projects_fts f JOIN projects p ON p.id=f.rowid WHERE projects_fts MATCH ? AND "
                   + " AND ".join(where) + " ORDER BY p.approved_2026 DESC LIMIT ?")
            rows = self.con.execute(sql, [q, *args, limit]).fetchall()
        else:
            rows = self.con.execute("SELECT * FROM projects WHERE " + " AND ".join(where) +
                                    " ORDER BY approved_2026 DESC LIMIT ?", [*args, limit]).fetchall()
        out = []
        for x in rows:
            out.append({"type": "project", "name": x["project"], "amount": x["approved_2026"], "lga": x["location_name"],
                        "mda": x["mda_name"], "spent_2025": x["perf_2025_jan_sep"], "budget_2025": x["revised_2025"],
                        "page": x["source_page"]})
        return out

    def retrieve(self, p):
        if p.intent == "project_status":
            return self.project_status(p)
        if p.intent == "ranking":
            return self.ranking(p)
        if p.intent == "overview":
            return self.overview(p)
        if p.intent == "lga":
            return self.lga(p, p.lga_codes[0])
        if p.intent == "mda":
            return self.mda(p, p.mda_codes[0])
        if p.intent == "function":
            return self.function(p, p.function_codes[0])
        if p.intent == "revenue":
            return self.revenue(p)
        if p.intent == "project":
            return self.project_search(p)
        return Retrieval(p.intent)
