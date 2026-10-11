"""Second held-out set, written after all fixes and run once without tuning: the honest generalisation estimate."""
import json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402
from app.fmt import naira  # noqa: E402
con = sqlite3.connect(str(config.BUDGET_DB))
fig = lambda v: sorted({naira(v, "ha"), naira(v, "en")}) if v else []
adm = lambda c, m="total": (con.execute("SELECT approved_2026 FROM line_items WHERE kind='exp_admin' AND measure=? AND code=?", (m, c)).fetchone() or [None])[0]
sp = lambda c: (con.execute("SELECT ytd_actual FROM perf_items WHERE report='2025Q4' AND kind='exp_admin' AND measure='total' AND code=?", (c,)).fetchone() or [None])[0]
H, E, A, W, S, WK, EN, LIV, ENV, YS = ("052100000000", "051700000000", "021500000000", "025200000000", "017000000000",
                                       "023400000000", "023100000000", "026800000000", "053500000000", "051300000000")
Q = []
def add(cat, lang, q, intents, **e):
    Q.append({"id": f"H2-{len(Q)+1:03d}", "category": cat, "difficulty": 3, "lang": lang, "question": q, "intents": intents, **e})
for q, l, c in [("Kudin da aka tsara wa harkar tsaro a 2026", "ha", S), ("How much has the government set aside for electricity this year?", "en", EN),
                ("Nawa ne kasafin kiwon dabbobi?", "ha", LIV), ("What is allocated for flood and erosion control in 2026?", "en", ENV),
                ("Matasa da wasanni, nawa aka ware musu?", "ha", YS), ("What's in the 2026 budget for farmers?", "en", A),
                ("Asibitoci nawa aka ware musu kudi?", "ha", H), ("2026 allocation to the education sector please", "en", E)]:
    add("alloc", l, q, ["mda"], mda=c, figures=fig(adm(c)))
for q, l, c in [("How much did security actually get in 2025?", "en", S), ("Nawa aka kashe a harkar ruwa a bara?", "ha", W),
                ("Electricity spending 2025", "en", EN), ("Kudin da aka kashe wa matasa da wasanni a 2025", "ha", YS)]:
    add("spent2025", l, q, ["mda"], mda=c, figures=fig(sp(c)))
for q, l, c in [("Wadanne ayyuka ne a Goronyo?", "ha", "33320500"), ("Silame projects", "en", "33311500"),
                ("Ayyukan da za a yi a Shagari a bana", "ha", "33331400"), ("What will be built in Sabon Birni?", "en", "33321300")]:
    add("lga", l, q, ["lga", "project"], lga=c)
for q, l, i in [("Which sector got the most money in 2026?", "en", ["ranking", "overview"]),
                ("Ayyukan da aka fara amma ba a gama ba a fannin noma", "ha", ["project_status"]),
                ("How many water projects carried over from 2025?", "en", ["project_status"]),
                ("Kasafin noma ya ragu ne ko ya karu?", "ha", ["mda"]), ("Biggest education projects in 2026", "en", ["ranking", "project", "mda"]),
                ("What percentage of the 2025 budget was implemented?", "en", ["overview"]),
                ("Nawa aka samu na kudaden shiga a 2025?", "ha", ["revenue"]), ("How much is the state paying pensioners?", "en", ["function"])]:
    add("analysis", l, q, i)
for q, l, i, e in [("helth 2026", "en", ["mda"], {"mda": H}), ("kasafin lafya", "ha", ["mda"], {"mda": H}),
                   ("how much for edu", "en", ["mda"], {"mda": E}), ("budget for agrculture", "en", ["mda"], {"mda": A})]:
    add("robust", l, q, i, **e)
for q, l in [("What is Bitcoin?", "en"), ("Ina ne kasuwar Sokoto take?", "ha"), ("Katsina state budget 2026", "en"), ("Who is the commissioner of finance?", "en")]:
    add("out_of_scope", l, q, ["out_of_scope", "none", "greeting"], scope="out")
(ROOT / "bench" / "holdout2.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in Q) + "\n", encoding="utf-8")
print(len(Q), "questions")
