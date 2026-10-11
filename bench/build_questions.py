"""Build the Kasafi benchmark: ~300 questions with expected answers computed from budget.sqlite.

Each question records what a correct answer needs:
  intents   accepted intents (how the question should be routed)
  mda / lga / func   the entity that must be recognised
  figures   amounts that must appear in the answer (formatted the way the bot writes them, Hausa or English)
  scope     "out" for questions the bot should decline (no budget figures)

Run:  python bench/build_questions.py      -> bench/questions.jsonl
"""
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402
from app.fmt import naira, pct, pct_str  # noqa: E402

random.seed(26)
con = sqlite3.connect(str(config.BUDGET_DB))
con.row_factory = sqlite3.Row
Q = []


def fig(v):
    return sorted({naira(v, "ha"), naira(v, "en")}) if v else []


def admin(code, measure="total", col="approved_2026"):
    r = con.execute(f"SELECT {col} FROM line_items WHERE kind='exp_admin' AND measure=? AND code=?", (measure, code)).fetchone()
    return r[0] if r else None


def spent25(code, measure="total"):
    r = con.execute("SELECT ytd_actual FROM perf_items WHERE report='2025Q4' AND kind='exp_admin' AND measure=? AND code=?",
                    (measure, code)).fetchone()
    return r[0] if r else None


def add(cat, diff, lang, q, intents, **exp):
    Q.append({"id": f"{cat}-{len([x for x in Q if x['category'] == cat]) + 1:03d}", "category": cat, "difficulty": diff,
              "lang": lang, "question": q, "intents": intents, **exp})


# ------------------------------------------------------------------ sectors (Hausa words / English words -> MDA)
SECTORS = [  # code, hausa word, english word
    ("052100000000", "lafiya", "health"), ("051700000000", "ilimi", "education"),
    ("056900000000", "ilimi mai zurfi", "higher education"), ("021500000000", "noma", "agriculture"),
    ("025200000000", "ruwan sha", "water supply"), ("023400000000", "hanyoyi", "roads"),
    ("017000000000", "tsaro", "security"), ("017200000000", "harkokin addini", "religious affairs"),
    ("051400000000", "harkokin mata", "women affairs"), ("051300000000", "matasa da wasanni", "youth and sports"),
    ("053500000000", "muhalli", "environment"), ("026800000000", "kiwon dabbobi", "livestock"),
    ("023100000000", "wutar lantarki", "energy"), ("025300000000", "gidaje da filaye", "housing and lands"),
    ("022200000000", "kasuwanci", "commerce"), ("022900000000", "sufuri", "transport"),
    ("012300000000", "yada labarai", "information"), ("031800000000", "kotuna", "the judiciary"),
    ("011200000000", "majalisar dokoki", "the House of Assembly"), ("055100000000", "kananan hukumomi", "local government affairs"),
    ("023800000000", "tsare-tsare", "budget and economic planning"), ("022000000000", "ma'aikatar kudi", "the Ministry of Finance"),
    ("016102100800", "'yan gudun hijira", "IDPs"), ("056905500100", "tallafin karatu", "scholarships"),
    ("052100300100", "kiwon lafiya matakin farko", "primary health care"), ("051700300100", "SUBEB", "SUBEB"),
]
SECTORS = [s for s in SECTORS if admin(s[0]) is not None]

HA_ALLOC = ["Nawa aka ware wa {w} a 2026?", "Kasafin {w} na 2026 nawa ne?", "Nawa ne kudin da aka ware wa {w} a bana?"]
EN_ALLOC = ["How much is allocated to {w} in 2026?", "What is the 2026 budget for {w}?", "How much did {w} get in the 2026 budget?"]
for i, (code, ha, en) in enumerate(SECTORS):
    v = admin(code)
    add("alloc", 1, "ha", HA_ALLOC[i % 3].format(w=ha), ["mda"], mda=code, figures=fig(v))
    add("alloc", 1, "en", EN_ALLOC[i % 3].format(w=en), ["mda"], mda=code, figures=fig(v))

HA_SPENT = ["Nawa aka kashe a fannin {w} a 2025?", "Nawa ne aka kashe wa {w} a shekarar 2025?"]
EN_SPENT = ["How much was spent on {w} in 2025?", "What was the actual spending on {w} in 2025?"]
for i, (code, ha, en) in enumerate(SECTORS[:18]):
    v = spent25(code)
    if v is None:
        continue
    add("spent2025", 2, "ha", HA_SPENT[i % 2].format(w=ha), ["mda"], mda=code, figures=fig(v))
    add("spent2025", 2, "en", EN_SPENT[i % 2].format(w=en), ["mda"], mda=code, figures=fig(v))

MEASURES = [("capital", "manyan ayyuka", "capital projects"), ("personnel", "albashi", "salaries"),
            ("overhead", "kudaden gudanarwa", "overhead")]
for code, ha, en in SECTORS[:8]:
    m, mha, men = MEASURES[len(Q) % 3]
    v = admin(code, m)
    if v:
        add("measure", 2, "ha", f"Nawa ne kudin {mha} na {ha} a 2026?", ["mda"], mda=code, figures=fig(v))
        add("measure", 2, "en", f"How much is the {men} budget for {en} in 2026?", ["mda"], mda=code, figures=fig(v))

def perf(code, report, measure="total"):
    return con.execute("SELECT budget_revised, ytd_actual FROM perf_items WHERE report=? AND kind='exp_admin' AND measure=? AND code=?",
                       (report, measure, code)).fetchone()


for i, (code, ha, en) in enumerate(SECTORS[:12]):
    r = perf(code, "2026Q2")
    if r and r["ytd_actual"]:
        add("spent2026", 2, "ha", f"Nawa aka kashe a fannin {ha} zuwa yanzu a 2026?", ["mda"], mda=code, figures=fig(r["ytd_actual"]))
        add("spent2026", 2, "en", f"How much has been spent on {en} so far in 2026?", ["mda"], mda=code, figures=fig(r["ytd_actual"]))
for i, (code, ha, en) in enumerate(SECTORS[:9]):
    r = perf(code, "2025Q4")
    if r and r["budget_revised"]:
        p_ = pct(r["ytd_actual"], r["budget_revised"])
        add("rate2025", 3, "ha", f"Kashi nawa aka aiwatar na kasafin {ha} a 2025?", ["mda"], mda=code,
            figures=sorted({pct_str(p_, "ha"), pct_str(p_, "en")}))
        add("rate2025", 3, "en", f"What percentage of the {en} budget was implemented in 2025?", ["mda"], mda=code,
            figures=sorted({pct_str(p_, "ha"), pct_str(p_, "en")}))
for code, ha, en in SECTORS[:4]:
    r = con.execute("SELECT actual_2023 FROM line_items_2025 WHERE kind='exp_admin' AND measure='total' AND code=?", (code,)).fetchone()
    if r and r[0]:
        add("history", 3, "en", f"How much was spent on {en} in 2023?", ["mda"], mda=code, figures=fig(r[0]))
        add("history", 3, "ha", f"Nawa aka kashe a fannin {ha} a 2023?", ["mda"], mda=code, figures=fig(r[0]))

# ------------------------------------------------------------------ agencies by their own (short) names
AGENCIES = [("Sultan Maccido Institute", "051700260100"), ("Fadama", None), ("Zakat and Endowment Agency", None),
            ("Hisbah", None), ("Almajiri agency", None), ("Pilgrims Welfare", None), ("Sokoto Road Maintenance Agency", None),
            ("Works School Sokoto", None), ("College of Agriculture Wurno", None), ("Arabic and Islamic Education Board", None),
            ("Department for Rural Roads", None), ("Hospitals Services Management Board", None), ("Specialist Hospital", None),
            ("Primary Health Care Development Agency", None), ("State Universal Basic Education Board", None),
            ("Shehu Shagari College of Education", None), ("Sokoto State Polytechnic", None), ("Radio Rima", None),
            ("Sokoto State Television", None), ("Ministry of Science and Technology", None)]
names = con.execute("SELECT code, name FROM line_items WHERE kind='exp_admin' AND measure='total' AND length(code)=12").fetchall()
for short, code in AGENCIES:
    if not code:
        words = [w.lower() for w in short.replace("agency", "").split() if len(w) > 3]
        cands = [r for r in names if all(w in r["name"].lower() for w in words)]
        if not cands:
            continue
        code = sorted(cands, key=lambda r: len(r["name"]))[0]["code"]
    v = admin(code)
    lang = "en" if len(Q) % 2 else "ha"
    q = f"How much did {short} get in 2026?" if lang == "en" else f"Nawa aka ware wa {short} a 2026?"
    add("agency", 2, lang, q, ["mda"], mda=code, figures=fig(v))

# ------------------------------------------------------------------ LGAs
LGAS = con.execute("SELECT DISTINCT location_code, location_name FROM projects WHERE location_code!='33342400'").fetchall()
for i, r in enumerate(LGAS):
    nm = r["location_name"].title()
    top = con.execute("SELECT project FROM projects WHERE location_code=? AND approved_2026>0 ORDER BY approved_2026 DESC LIMIT 1",
                      (r["location_code"],)).fetchone()
    hint = [top[0][:40]] if top else []
    add("lga", 1, "ha", ["Wadanne ayyuka ne za a yi a {n}?", "Ayyukan raya kasa a karamar hukumar {n}", "Me aka tsara wa {n} a kasafin 2026?"][i % 3].format(n=nm),
        ["lga"], lga=r["location_code"], texts=hint)
    if i % 2 == 0:
        add("lga", 1, "en", f"What projects are planned in {nm} LGA?", ["lga"], lga=r["location_code"], texts=hint)
for nm in ["Gudu", "Rabah", "Tureta"]:   # real LGAs with no projects tagged to them in the budget
    add("lga_untagged", 3, "ha", f"Wadanne ayyuka ne a {nm}?", ["lga", "project"], texts=[])
    add("lga_untagged", 3, "en", f"What projects are in {nm} local government?", ["lga", "project"], texts=[])

# ------------------------------------------------------------------ cross-cutting functions
for ha, en, code in [("kariyar zamantakewa", "social protection", "710"), ("fansho", "pensions", "7102"),
                     ("marasa aikin yi", "unemployment", "7105")]:
    add("function", 2, "ha", f"Nawa aka ware wa {ha} a 2026?", ["function"], func=code)
    add("function", 2, "en", f"How much is budgeted for {en} in 2026?", ["function"], func=code)
    add("function", 3, "en", f"How much was spent on {en} in 2025?", ["function"], func=code)

# ------------------------------------------------------------------ revenue
for q, lang in [("Nawa ne kudaden shigar jiha?", "ha"), ("Nawa ne kudaden shiga na cikin gida (IGR) a 2026?", "ha"),
                ("Nawa jiha ta samu daga asusun tarayya a 2025?", "ha"), ("What is the state's total revenue for 2026?", "en"),
                ("How much IGR is the state expecting in 2026?", "en"), ("How much FAAC did Sokoto receive in 2025?", "en"),
                ("How much revenue has the state received so far in 2026?", "en"), ("Kudaden shiga nawa aka samu a 2025?", "ha")]:
    add("revenue", 2, lang, q, ["revenue"])

# ------------------------------------------------------------------ overview
tot = admin("")
for q, lang in [("Menene jimillar kasafin kudin jihar Sokoto na 2026?", "ha"), ("Nawa ne kasafin 2026?", "ha"),
                ("What is the total 2026 budget of Sokoto State?", "en"), ("How big is the Sokoto budget this year?", "en"),
                ("Nawa aka kashe a jimilla a 2025?", "ha"), ("What was the overall implementation rate of the 2025 budget?", "en")]:
    add("overview", 1 if "2026" in q else 2, lang, q, ["overview"], figures=fig(tot) if "2026" in q or "this year" in q else [])

# ------------------------------------------------------------------ project search
for q, lang in [("Ayyukan rijiyoyin burtsatse nawa ne a kasafin?", "ha"), ("Ina ake gina asibitoci a 2026?", "ha"),
                ("Solar street lights projects", "en"), ("Which projects build classrooms?", "en"),
                ("Ayyukan gyaran makarantu", "ha"), ("Show me road construction projects in Tambuwal", "en"),
                ("Projects for drug addiction centres", "en"), ("Ayyukan samar da ruwan sha a Wamakko", "ha"),
                ("Are there projects for IDP camps?", "en"), ("Ayyukan gina masallatai", "ha"),
                ("fertilizer procurement projects 2026", "en"), ("Rehabilitation of hospitals projects", "en")]:
    add("project", 2, lang, q, ["project", "lga", "mda", "function"], wants_items=True)

# ------------------------------------------------------------------ analysis
for q, lang, intents in [
    ("Ayyuka nawa aka fara a 2025 kuma har yanzu suna ci gaba a 2026?", "ha", ["project_status"]),
    ("How many projects started in 2025 are still ongoing in 2026?", "en", ["project_status"]),
    ("How many health projects were budgeted in 2025 but nothing was spent?", "en", ["project_status"]),
    ("Ayyukan ilimi nawa ne ba a kashe ko sisi ba a 2025?", "ha", ["project_status"]),
    ("Which new projects are in the 2026 budget for water?", "en", ["project_status", "project"]),
    ("Ayyuka nawa aka daina daga 2025 zuwa 2026?", "ha", ["project_status"]),
    ("how many projects have been done for IDPs in Sokoto in 2025", "en", ["project_status"]),
    ("Ko ana samun ci gaba ga ayyukan social protection a jihar Sokoto?", "ha", ["project_status"]),
    ("Project status in Wamakko", "en", ["project_status"]),
    ("Ayyuka nawa ne ke ci gaba a karamar hukumar Tambuwal?", "ha", ["project_status"]),
    ("Which ministry got the largest budget in 2026?", "en", ["ranking"]),
    ("Wace ma'aikata ce ta fi samun kudi a 2026?", "ha", ["ranking"]),
    ("Which ministry had the lowest capital implementation in 2025?", "en", ["ranking"]),
    ("Wace ma'aikata ce ta fi karancin aiwatar da kasafin 2025?", "ha", ["ranking"]),
    ("Which LGA has the most projects in 2026?", "en", ["ranking"]),
    ("Wace karamar hukuma ce ta fi samun ayyuka?", "ha", ["ranking"]),
    ("Which ministry's budget increased the most from 2025 to 2026?", "en", ["ranking"]),
    ("Which ministry was cut the most in 2026?", "en", ["ranking"]),
    ("What are the 5 biggest projects in 2026?", "en", ["ranking", "project"]),
    ("Mafi girman aiki a kasafin 2026 wanne ne?", "ha", ["ranking", "project"]),
    ("Compare health spending in 2024, 2025 and 2026", "en", ["mda"]),
    ("Yaya kasafin ilimi ya canza tun 2023?", "ha", ["mda"]),
    ("Has the agriculture budget increased compared to last year?", "en", ["mda"]),
    ("Kasafin lafiya ya karu ko ya ragu daga bara?", "ha", ["mda"]),
    ("How did the works ministry budget change between 2025 and 2026?", "en", ["mda"]),
]:
    add("analysis", 4 if intents[0] in ("project_status", "ranking") else 3, lang, q, intents)

# ------------------------------------------------------------------ robustness: typos, ASR-style errors, Pidgin, code-switching
for q, lang, intents, ent in [
    ("nawa aka ware wa lafia a 2026", "ha", ["mda"], {"mda": "052100000000"}),
    ("nawa aka ware wa ilmi 2026", "ha", ["mda"], {"mda": "051700000000"}),
    ("kasafin kudin lafiya", "ha", ["mda"], {"mda": "052100000000"}),
    ("NAWA AKA WARE WA NOMA", "ha", ["mda"], {"mda": "021500000000"}),
    ("nawa aka wa re wa ma aikatar lafiya", "ha", ["mda"], {"mda": "052100000000"}),
    ("How much dem give health for 2026?", "en", ["mda"], {"mda": "052100000000"}),
    ("How much money government put for education this year?", "en", ["mda"], {"mda": "051700000000"}),
    ("health budget 2026", "en", ["mda"], {"mda": "052100000000"}),
    ("Nawa aka ware for agriculture a 2026?", "ha", ["mda"], {"mda": "021500000000"}),
    ("allocation to ministry of health 2026 nawa ne", "ha", ["mda"], {"mda": "052100000000"}),
    ("How much was spent on helth in 2025", "en", ["mda"], {"mda": "052100000000"}),
    ("edu budget 2026", "en", ["mda"], {"mda": "051700000000"}),
    ("nawa aka kashe a fanin ilimi a shekarar da ta wuce", "ha", ["mda"], {"mda": "051700000000"}),
    ("ayyukan tambuwal", "ha", ["lga"], {"lga": "33331800"}),
    ("projects in sokoto north", "en", ["lga"], {"lga": "33311600"}),
    ("Wamako projects", "en", ["lga"], {"lga": "33312100"}),
    ("dange shuni ayyuka", "ha", ["lga"], {"lga": "33330300"}),
    ("nawa ne kudin 'yan fansho", "ha", ["function"], {"func": "7102"}),
    ("social protection 2025 spending", "en", ["function"], {"func": "710"}),
    ("o ana samun shi gaba ga ayyuka na social protection a jihar sokoto.", "ha", ["project_status"], {}),
    ("Nawa ake biyan albashi a ma'aikatar ilimi?", "ha", ["mda"], {"mda": "051700000000"}),
    ("Kudin gyaran hanyoyi nawa ne a 2026?", "ha", ["mda", "project"], {}),
    ("water", "en", ["mda"], {"mda": "025200000000"}),
    ("lafiya", "ha", ["mda"], {"mda": "052100000000"}),
    ("How much is for infrastructure in 2026", "en", ["mda"], {"mda": "023400000000"}),
]:
    add("robust", 3, lang, q, intents, **ent)

# ------------------------------------------------------------------ greetings and out of scope (must not invent budget answers)
for q, lang, intents in [("Sannu", "ha", ["greeting"]), ("Assalamu alaikum", "ha", ["greeting"]), ("Hello", "en", ["greeting"]),
                         ("Ina kwana?", "ha", ["greeting"])]:
    add("greeting", 1, lang, q, intents)
for q, lang in [("Who is the governor of Sokoto State?", "en"), ("What is the weather in Sokoto today?", "en"),
                ("Tell me a joke", "en"), ("Nawa ne farashin buhun shinkafa a kasuwa?", "ha"),
                ("Wanene shugaban kasar Najeriya?", "ha"), ("What is the capital of Nigeria?", "en"),
                ("How much is the Kano State budget?", "en"), ("Nawa ne kasafin jihar Zamfara?", "ha"),
                ("What is the federal budget for 2026?", "en"), ("Can you write me a poem?", "en")]:
    add("out_of_scope", 3, lang, q, ["none", "greeting"], scope="out")

# ------------------------------------------------------------------ multi-entity (known limitation: one subject per question)
for q, lang in [("Compare health and education budgets in 2026", "en"), ("Nawa aka ware wa lafiya da ilimi a 2026?", "ha"),
                ("How much for services, agriculture and industry?", "en"), ("Health vs agriculture 2025 spending", "en")]:
    add("multi", 4, lang, q, ["mda", "comparison", "function", "overview"], multi=True)

out = ROOT / "bench" / "questions.jsonl"
out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in Q) + "\n", encoding="utf-8")
cats = {}
for x in Q:
    cats[x["category"]] = cats.get(x["category"], 0) + 1
print(f"{len(Q)} questions -> {out}")
print(cats)
