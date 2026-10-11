"""Held-out benchmark: new wording and entities, written AFTER the fixes and never used to tune them.
Its score is the honest estimate of how the bot handles questions it hasn't seen.

Run:  python bench/build_holdout.py   -> bench/holdout.jsonl
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402
from app.fmt import naira  # noqa: E402

con = sqlite3.connect(str(config.BUDGET_DB))
Q = []


def fig(v):
    return sorted({naira(v, "ha"), naira(v, "en")}) if v else []


def admin(code, measure="total"):
    r = con.execute("SELECT approved_2026 FROM line_items WHERE kind='exp_admin' AND measure=? AND code=?", (measure, code)).fetchone()
    return r[0] if r else None


def spent25(code, measure="total"):
    r = con.execute("SELECT ytd_actual FROM perf_items WHERE report='2025Q4' AND kind='exp_admin' AND measure=? AND code=?",
                    (measure, code)).fetchone()
    return r[0] if r else None


def add(cat, diff, lang, q, intents, **exp):
    Q.append({"id": f"H-{cat}-{len([x for x in Q if x['category'] == cat]) + 1:03d}", "category": cat, "difficulty": diff,
              "lang": lang, "question": q, "intents": intents, **exp})


H, E, A, W = "052100000000", "051700000000", "021500000000", "025200000000"
S, WK, INF, HE = "017000000000", "023400000000", "012300000000", "056900000000"

# allocation, new wording
for q, lang, code in [
    ("Me aka ware wa ma'aikatar noma a kasafin bana?", "ha", A), ("Kudin da aka ware wa asibitoci nawa ne a 2026?", "ha", H),
    ("Gwamnati ta ware nawa ga ruwan sha a 2026?", "ha", W), ("Kasafin ma'aikatar yada labarai na 2026", "ha", INF),
    ("What's the education ministry's budget for 2026?", "en", E), ("How much money goes to security in 2026?", "en", S),
    ("Ministry of Works allocation 2026", "en", WK), ("How much is the Ministry for Higher Education getting in 2026?", "en", HE),
    ("Nawa gwamnati ta tanada wa harkar lafiya a bana?", "ha", H), ("Tell me the 2026 budget for agriculture", "en", A),
]:
    add("alloc", 1, lang, q, ["mda"], mda=code, figures=fig(admin(code)))

# spending 2025, new wording
for q, lang, code in [
    ("A 2025 nawa aka kashe wa tsaro?", "ha", S), ("Spending on agriculture last year", "en", A),
    ("What did the works ministry actually spend in 2025?", "en", WK), ("Nawa ma'aikatar ilimi ta kashe a bara?", "ha", E),
    ("How much of the health budget was used in 2025?", "en", H), ("Kudin da aka kashe a ruwan sha a 2025", "ha", W),
]:
    add("spent2025", 2, lang, q, ["mda"], mda=code, figures=fig(spent25(code)))

# measures
for q, lang, code, m in [
    ("Nawa ne albashin ma'aikatan lafiya a 2026?", "ha", H, "personnel"), ("Capital allocation for health 2026", "en", H, "capital"),
    ("Education overhead 2026", "en", E, "overhead"), ("Manyan ayyukan ma'aikatar noma a 2026 nawa ne?", "ha", A, "capital"),
    ("How much will the water ministry pay in salaries in 2026?", "en", W, "personnel"),
]:
    add("measure", 2, lang, q, ["mda"], mda=code, figures=fig(admin(code, m)))

# agencies
for q, lang, words in [
    ("How much does the Water Board get in 2026?", "en", ["water board"]),
    ("Nawa aka ware wa Rural Water and Sanitation Agency?", "ha", ["rural water and sanitation"]),
    ("Budget for the Sokoto State Emergency Management Agency 2026", "en", ["emergency management"]),
    ("How much was released to SUBEB in 2025?", "en", ["universal basic education board"]),
    ("Kasafin Hukumar Zakka da Wakafi", "ha", ["zakat"]),
    ("What did the judiciary spend in 2025?", "en", None),
]:
    if words:
        r = con.execute("SELECT code FROM line_items WHERE kind='exp_admin' AND measure='total' AND length(code)=12 AND "
                        + " AND ".join("lower(name) LIKE ?" for _ in words) + " ORDER BY length(name) LIMIT 1",
                        [f"%{w}%" for w in words]).fetchone()
        code = r[0] if r else None
    else:
        code = "031800000000"
    if code:
        add("agency", 2, lang, q, ["mda"], mda=code)

# LGAs
for q, lang, code in [
    ("Ayyukan raya kasa na Illela", "ha", "33320800"), ("Me za a yi a Bodinga a 2026?", "ha", "33330200"),
    ("Ayyukan Sokoto ta Kudu", "ha", "33311700"), ("Projects in Sokoto South", "en", "33311700"),
    ("borehole projects in Kebbe", "en", "33331000"), ("What is planned for Yabo?", "en", "33332300"),
    ("Ayyukan karamar hukumar Kware", "ha", "33311100"), ("Gwadabawa LGA projects 2026", "en", "33320700"),
]:
    add("lga", 1, lang, q, ["lga", "project"], lga=code)

# functions, revenue, overview
add("function", 2, "ha", "Nawa ake biya 'yan fansho a 2026?", ["function"], func="7102")
add("function", 2, "en", "Budget for the poor and vulnerable in 2026", ["function"], func="710")
add("revenue", 2, "ha", "Kudin shigar jiha daga haraji nawa ne?", ["revenue"])
add("revenue", 2, "en", "How much does Sokoto expect from FAAC in 2026?", ["revenue"])
add("revenue", 2, "en", "Internally generated revenue 2025", ["revenue"])
add("overview", 1, "ha", "Kasafin 2026 ya kai nawa?", ["overview"], figures=fig(admin("")))
add("overview", 1, "en", "Total salaries in the 2026 budget", ["overview"])
add("overview", 2, "en", "How much of the 2025 budget was actually spent?", ["overview"])

# projects and analysis
for q, lang, intents in [
    ("List road projects", "en", ["project", "mda"]), ("solar projects", "en", ["project", "mda"]),
    ("Wane aiki ne mafi tsada a fannin lafiya?", "ha", ["ranking", "project", "mda"]),
    ("Top 3 ministries by allocation", "en", ["ranking"]), ("Which LGA gets the least projects?", "en", ["ranking"]),
    ("How many projects are new in 2026?", "en", ["project_status"]), ("Ayyukan hanya nawa ne a Wamakko?", "ha", ["project_status", "lga", "project"]),
    ("Has security funding gone up?", "en", ["mda"]), ("Shin an kara kudin ilimi a 2026?", "ha", ["mda"]),
    ("Which projects got money in 2025 but nothing was spent?", "en", ["project_status"]),
]:
    add("analysis", 3, lang, q, intents, wants_items=intents[0] == "project")

# robustness
for q, lang, intents, ent in [
    ("lafiya 2026 nawa", "ha", ["mda"], {"mda": H}), ("nawa aka warewa ilimi", "ha", ["mda"], {"mda": E}),
    ("how much 4 health", "en", ["mda"], {"mda": H}), ("agric budget", "en", ["mda"], {"mda": A}),
    ("budget 4 water 2026", "en", ["mda"], {"mda": W}), ("kasafin kudin ma'aikatar lafia", "ha", ["mda"], {"mda": H}),
    ("spendin on edukation 2025", "en", ["mda"], {"mda": E}), ("tsaro nawa aka ware", "ha", ["mda"], {"mda": S}),
]:
    add("robust", 3, lang, q, intents, **ent)

# out of scope
for q, lang in [("Who won the 2023 election?", "en"), ("What's the dollar rate today?", "en"),
                ("Nawa ne kudin mota zuwa Kano?", "ha"), ("Write a letter for me", "en"), ("Wanene kwamishinan lafiya?", "ha"),
                ("What is the Lagos State budget for 2026?", "en")]:
    add("out_of_scope", 3, lang, q, ["none", "greeting", "out_of_scope"], scope="out")

out = ROOT / "bench" / "holdout.jsonl"
out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in Q) + "\n", encoding="utf-8")
print(f"{len(Q)} held-out questions -> {out}")
