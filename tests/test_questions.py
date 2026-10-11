"""Regression checks for question routing and grounded figures (no GPU needed).

Run: python -m tests.test_questions
"""
import os
import sys
from pathlib import Path
import tempfile

os.environ["LLM_BACKEND"] = "none"
os.environ["ASR_ENABLED"] = "0"
os.environ["LOG_DB"] = os.path.join(tempfile.mkdtemp(), "test_log.sqlite")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine import Engine  # noqa: E402

CASES = [
    ("how much was spent for Sultan Maccido Institute", "Sultan Maccido Institute"),       # short form of an agency name
    ("How much was allocated for Infrastructure in 2026", "Ministry of Works"),  # question, expected text in the answer
    ("Nawa aka ware wa lafiya a 2026?", "₦124.41 biliyan"),
    ("Nawa aka kashe a fannin ilimi a 2025?", "₦38.22 biliyan"),
    ("Wadanne ayyuka ne za a yi a Tambuwal?", "Karamar Hukumar Tambuwal"),
    ("Ayyukan rijiyoyin burtsatse nawa ne a kasafin?", "borehole"),
    ("Nawa ne kudaden shigar jiha?", "₦389.32 biliyan"),
    ("How much is allocated to agriculture in 2026?", "₦17.05 billion"),
    ("Nawa ne albashin ma'aikatar ilimi?", "₦12.12 biliyan"),
    ("Menene jimillar kasafin kudin 2026?", "₦758.7 biliyan"),
    ("How much did SUBEB spend in 2025?", "₦4.58 billion"),
    ("Nawa ne bashin da jihar za ta biya?", "₦19.76 biliyan"),
    ("Ma'aikatar ayyuka nawa aka ware mata?", "Ministry of Works"),
    ("Nawa aka ware wa harkokin mata?", "Ministry for Women Affairs"),
    ("Kudin tallafin karatu nawa ne?", "Scholarship"),
    ("ina son sanin kasafin Gwadabawa", "Gwadabawa"),
    ("Sannu", "Kasafi Bot"),
    ("nawa aka warewa social protection a 2026 a sokoto?", "₦34.37 biliyan"),
    ("Nawa aka ware wa 'yan fansho?", "₦10.27 biliyan"),
    ("Menene kasafin 2026?", "₦758.7 biliyan"),
    ("nawa aka ware wa wani abu da ba a sani ba?", "Yi hakuri"),
    ("ayyuka, wanda ke karkashin ma'aikatan lafiyar, guda nawa ne aka fara a 2025 bakari su ba'ar 2026.", ": 97"),
    ("How many projects started in 2025 are still ongoing in 2026?", "continuing in 2026: 811"),
    ("Wace ma'aikata ce ta fi samun kudi a kasafin 2026?", "1. Ministry of Health"),
    ("Which ministries had the lowest capital implementation in 2025?", "1. State Judiciary"),
    ("Wace karamar hukuma ce ta fi samun kudi?", "1. Wamakko"),
    ("Kasafin lafiya ya karu idan aka kwatanta da 2025?", "kashi 197.1"),
    ("Nawa aka kashe daga kasafin 2026 zuwa yanzu?", "Janairu-Yuni 2026"),
    ("Nawa aka ware wa lafiya a 2026?", "kashi 10.6"),
    ("How much IGR did the state collect in 2025?", "₦20.58 billion"),
    ("Yaya kasafin lafiya ya canza tun 2023?", "₦13.23 biliyan"),
    ("Nawa aka kashe a fannin ilimi a 2025?", "kafin gyara"),
    ("Nawa aka kashe a fannin lafiya a 2024?", "Jan-Sat 2024"),
]


def speech_checks():
    from app.speak import number_words, to_speech
    cases = [(number_words(2026), "dubu biyu da ashirin da shida"), (number_words(15), "goma sha biyar"),
             (number_words(124410000000), "biliyan dari da ashirin da hudu da miliyan dari hudu da goma"),
             (to_speech("An kashe kashi 10.6 cikin 100."), "kashi goma ɗigo shida cikin ɗari"),
             # every order N-ATLaS writes money in
             (to_speech("An kashe Naira biliyan 8.75 a 2025."), "naira biliyan takwas da miliyan ɗari bakwai da hamsin"),
             (to_speech("An kashe biliyan 16.22."), "biliyan goma sha shida da miliyan ɗari biyu da ashirin"),
             (to_speech("Kasafin ya kai ₦32.85 biliyan."), "naira biliyan talatin da biyu da miliyan ɗari takwas da hamsin"),
             (to_speech("An kashe 16.22 biliyan."), "biliyan goma sha shida"),
             (to_speech("An kashe kashi 49.4%."), "kashi arba'in da tara ɗigo huɗu cikin ɗari"),
             (to_speech("A 2025, an kashe."), "biyar, an kashe"),
             (to_speech("Karamar Hukumar Tambuwal"), "ƙaramar hukumar tambuwal")]
    bad = [(got, want) for got, want in cases if want not in got]
    bad += [(c[0], "no digits") for c in cases if any(ch.isdigit() for ch in c[0])]
    for got, want in bad:
        print(f"FAIL speech: expected '{want}' in '{got}'")
    print(f"speech: {len(cases) - len(bad)}/{len(cases)} passed")
    return len(bad)


def year_checks():
    """A 2025 question must not be answered with a 2026 figure (real bug: social protection 2025 got the
    2026 'Social Protection (other)' allocation, ₦8.75bn, instead of ₦16.22bn spent)."""
    class FakeLLM:
        enabled, model_id = True, "fake"
        def __init__(self, draft): self.draft = draft
        def understand(self, text): return {}
        def write(self, q, facts, lang): self.facts = facts; return self.draft
    e = Engine(load_models=False)
    q = "nawa aka kashe a social protection a shekara ta 2025 a sokoto?"
    fails = 0
    e.llm = FakeLLM("An kashe Naira biliyan 8.75 a fannin kare zamantakewa a shekarar 2025.")
    r = e.handle_text("test", "t", q)
    if "8.75" in e.llm.facts or not r.text.lstrip().startswith("*"):
        print("FAIL year: wrong-year figure reached N-ATLaS or passed the grounding check"); fails += 1
    if "16.22" not in r.text:
        print("FAIL year: template answer lacks the 2025 spend"); fails += 1
    e.llm = FakeLLM("A shekarar 2025, an kashe ₦16.22 biliyan, kashi 49.4 cikin 100 na kasafin ₦32.85 biliyan.")
    r = e.handle_text("test", "t", q)
    if not r.text.startswith("A shekarar 2025") or "Rabe-rabensa (2026)" not in r.text:
        print("FAIL year: correct 2025 draft rejected, or 2026 breakdown not shown under it"); fails += 1
    print(f"year focus: {3 - fails}/3 passed")
    return fails


def claim_checks():
    """Spent vs allocated: a real number described as the wrong thing must be rejected (live failure: a 2026
    sub-category allocation, ₦8.75bn, was written as 'aka kashe' for social protection)."""
    from app.answer import grounded
    e = Engine(load_models=False)
    R = lambda q: e.store.retrieve(e.nlu.parse(q))
    fr, er = R("Nawa aka ware wa social protection?"), R("Nawa aka kashe a fannin ilimi a 2025?")
    sr = R("Ko ana samun ci gaba ga ayyukan social protection a jihar Sokoto?")
    cases = [
        (fr, "Kudaden da aka kashe na Social Protection (sauran) a cikin kasafin kudin Jihar Sokoto na 2026 shine ₦8.75 biliyan.", False),
        (fr, "An ware ₦34.37 biliyan don kariyar zamantakewa a kasafin 2026. A 2025 an kashe ₦16.22 biliyan.", True),
        (fr, "An ware ₦34.37 biliyan a 2026, amma zuwa watan Yuni an kashe ₦8.11 biliyan.", True),
        (er, "A 2025 an kashe ₦38.22 biliyan a fannin ilimi daga kasafin ₦57.2 biliyan.", True),
        (er, "An ware ₦38.22 biliyan ga ilimi a 2025.", False),
        (sr, "An ware musu ₦7.47 biliyan a 2025 amma ba a kashe ko sisi ba.", True),
    ]
    fails = 0
    for r, draft, want in cases:
        ok, why = grounded(draft, r, "ha")
        if ok != want:
            print(f"FAIL claim: {draft[:70]} -> {ok} {why or ''}"); fails += 1
    mr = R("How much did the Department for IDPs Matters spend in 2025?")
    ok, _ = grounded("In 2025 the government spent ₦4.8 million on capital projects for IDPs.", mr, "en")
    if ok:   # live failure: the department's TOTAL spending presented as capital spending (capital was ₦0)
        print("FAIL claim: total figure presented as capital was accepted"); fails += 1
    wr = R("How much was allocated for Infrastructure in 2026")
    if grounded("The total budget allocated for Infrastructure in 2026 is ₦58.13 billion.", wr, "en")[0]:
        print("FAIL claim: capital part presented as the total was accepted"); fails += 1   # live: total is ₦59.17bn
    if not grounded("The Ministry of Works has ₦59.17 billion in 2026, of which ₦58.13 billion is for capital projects.", wr, "en")[0]:
        print("FAIL claim: correct total + capital sentence rejected"); fails += 1
    mc = R("how much was spent for Sultan Maccido Institute")
    if grounded("The Sultan Maccido Institute was not mentioned in the provided facts.", mc, "en")[0]:
        print("FAIL claim: 'not mentioned' answer accepted although figures exist"); fails += 1
    if e.nlu.parse("how many projects have been done for IDPs in Sokoto in 2025").intent != "project_status":
        print("FAIL claim: 'how many projects ... for IDPs' not routed to project status"); fails += 1
    if e.nlu.parse("o ana samun shi gaba ga ayyuka na social protection a jihar sokoto.").intent != "project_status":
        print("FAIL claim: ASR variant 'shi gaba' (ci gaba) not routed to project status"); fails += 1
    # "nawa" before the verb is "how much", not "how many": money questions about works/projects stay money answers
    routing = [("Nawa aka ware wa ayyukan ilimi a 2026?", "mda"), ("Ma'aikatar ayyuka nawa aka ware mata?", "mda"),
               ("Nawa aka ware wa ayyukan lafiya?", "mda"), ("Ayyuka nawa ne a Tambuwal?", "project_status"),
               # "state finances" is the whole budget, not the Ministry of Finance ("Finance" alone still is the ministry)
               ("How are the state finances in 2026?", "overview"), ("How much is allocated to Finance in 2026", "mda")]
    for q, want in routing:
        got = e.nlu.parse(q).intent
        if got != want:
            print(f"FAIL claim: '{q}' routed to {got}, expected {want}"); fails += 1
    # full-year (Q4) project spending is shown with the Q4 final budget, not the 2026 budget's mid-year 2025 column
    # (UBEC: ₦1.55bn revised vs ₦5.05bn final, ₦3.61bn spent would read as a 232% overspend)
    over = [pid for pid, (sp, _pg, bf) in e.store.full_proj.items() if bf and sp > bf + 1]
    shown = [e.store._proj_item(x, "", "") for x in e.store.con.execute(
        f"SELECT * FROM projects WHERE id IN ({','.join('?' * len(e.store.full_proj))})", list(e.store.full_proj)).fetchall()]
    if over or any(i["spent_2025"] > (i["budget_2025"] or 0) + 1 for i in shown):
        print("FAIL claim: a full-year project shows more spent than its 2025 budget"); fails += 1
    print(f"claims: {len(cases) + 7 + len(routing) - fails}/{len(cases) + 7 + len(routing)} passed")
    return fails


PHC_Q = ("How much money from the 2025 state budget is specifically designated to renovate primary health centers in Sokoto "
         "South LGA, and according to the latest performance report, has any of that money actually been spent yet?")


def natlas_replay_checks():
    """Replays answers the real N-ATLaS gave in the Colab benchmark run (bench/results_llm.jsonl)."""
    class Fake:
        enabled, model_id = True, "fake"
        def __init__(self, und, draft): self.und, self.draft = und, draft
        def understand(self, text): return self.und
        def write(self, q, facts, lang): return self.draft
    e = Engine(load_models=False)
    fails = 0
    cases = [  # question, N-ATLaS understanding, N-ATLaS draft, must contain, must be written by N-ATLaS?
        ("How much did Fadama get in 2026?", {"english": "How much did Fadama get in 2026?", "wants": "allocation", "year": 2026},
         "The Fadama Programme received ₦800 thousand in 2026.", "₦2.6", False),
        ("How much did Hisbah get in 2026?", {"english": "How much did Hisbah get in 2026?", "wants": "allocation", "year": 2026},
         "The Hisbah Board received ₦889.67 million in 2026.", "₦889.67", True),
        ("Kashi nawa aka aiwatar na kasafin lafiya a 2025?", {"english": "What percentage of the health budget was implemented in 2025?",
         "topic": "health", "wants": "spending", "year": 2025}, "An aiwatar da kashi 41.8 na kasafin lafiya a 2025.", "41.8", True),
        ("Nawa ne kudaden shiga na cikin gida (IGR) a 2026?", {"english": "How much is the internally generated revenue (IGR) in 2026?",
         "topic": "internal revenue", "wants": "revenue", "year": 2026}, "Kudaden shiga na cikin gida (IGR) a 2026 ya kai ₦180 miliyan.",
         "Kudaden shigar jiha", False),
        ("Wadanne ayyuka ne za a yi a Wamakko?", {"english": "What projects will be carried out in Wamakko?", "topic": "Wamakko",
         "wants": "project_status"}, "", "Karamar Hukumar Wamakko", False),
        ("Nawa aka ware wa kariyar zamantakewa a 2026?", {"english": "How much was allocated to social protection in 2026?",
         "topic": "social protection", "wants": "allocation", "year": 2026},
         "An ware ₦34.37 biliyan don kariyar zamantakewa a 2026, ciki har da manyan ayyuka ₦13.88 biliyan.", "₦34.37", True),
        # live Telegram, 11 Oct: a "no money" answer with no figure, while ₦7.89bn of state-wide PHC renovation existed
        # live again after the first fix: N-ATLaS's hint "primary health center renovation projects" + "project_status"
        (PHC_Q, {"english": PHC_Q, "topic": "primary health center renovation projects", "wants": "project_status", "year": 2025},
         "No money from the 2025 state budget is designated to renovate primary health centers in Sokoto South LGA, and no money "
         "has been spent yet according to the latest performance report.", "₦7.89", False),
        (PHC_Q, {"english": PHC_Q, "wants": "spending", "year": 2025},
         "No money from the 2025 state budget is specifically designated to renovate primary health centers in Sokoto South LGA, "
         "and no money has been spent yet according to the latest performance report.", "₦7.89", False),
        (PHC_Q, {"english": PHC_Q, "wants": "spending", "year": 2025},
         "No PHC renovation project is tagged to Sokoto South LGA. State-wide, ₦7.89 billion was budgeted in 2025 to renovate 244 "
         "ward-level health facilities, and ₦427.17 million of it was spent in the full year 2025.", "₦427.17", True),
    ]
    for q, und, draft, must, natlas in cases:
        e.llm = Fake(und, draft)
        r = e.handle_text("test", "t", q)
        src = (e.logs.admin_get(r.interaction_id) or {}).get("answer_source")
        if must not in r.text or (natlas and src != "natlas") or (not natlas and src == "natlas"):
            print(f"FAIL replay: {q} -> source {src}\n{r.text[:200]}"); fails += 1
    print(f"N-ATLaS replay: {len(cases) - fails}/{len(cases)} passed")
    return fails


def onboarding_checks():
    import tempfile
    from app.logstore import LogStore
    from app.onboarding import Onboarding
    ob = Onboarding(LogStore(Path(tempfile.mkdtemp()) / "t.sqlite"))
    fails = 0
    steps = [ob.step("u1", "whatsapp", "join silver-cat"), ob.step("u1", "whatsapp", "Nawa aka ware wa lafiya a 2026?"),
             ob.step("u1", "whatsapp", "Aminu Bello"), ob.step("u1", "whatsapp", "babu")]
    want = [(False, "name"), (False, "name"), (False, "org"), (True, None)]
    for st, (done, stage) in zip(steps, want):
        if st.done != done or st.stage != stage:
            print(f"FAIL onboarding: {st}"); fails += 1
    if steps[-1].pending != "Nawa aka ware wa lafiya a 2026?":
        print("FAIL onboarding: question asked during registration was not kept"); fails += 1
    u = ob.profile("u1")
    if not u or u["name"] != "Aminu Bello" or u["organization"] != "None":
        print(f"FAIL onboarding: profile {u}"); fails += 1
    v = [ob.step("u2", "whatsapp", "", pending="media:audio/ogg|https://x/1"), ob.step("u2", "whatsapp", "Hauwa"),
         ob.step("u2", "whatsapp", "UNICEF")]
    if v[-1].pending != "media:audio/ogg|https://x/1":
        print("FAIL onboarding: voice note sent before registering was not kept"); fails += 1
    st = ob.step("u3", "telegram", "hi")
    st = ob.step("u3", "telegram", "Nawa aka ware wa lafiya")      # short question, no "?": must not become the name
    if st.stage != "name" or ob.logs.get_user("u3")["name"]:
        print("FAIL onboarding: a short question was saved as a name"); fails += 1
    if "adana" not in ob.step("u4", "telegram", "hello").reply:
        print("FAIL onboarding: privacy notice missing from the first prompt"); fails += 1
    print(f"onboarding: {'OK' if not fails else f'{fails} failures'}")
    return fails


def main():
    speech_fails = speech_checks() + year_checks() + onboarding_checks() + claim_checks() + natlas_replay_checks()
    e = Engine(load_models=False)
    fails = 0
    for q, want in CASES:
        a = e.handle_text("test", "t", q).text
        ok = want in a
        fails += not ok
        print(("PASS" if ok else "FAIL"), q, "" if ok else f"\n  expected '{want}' in:\n{a[:300]}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
    sys.exit(1 if fails or speech_fails else 0)


if __name__ == "__main__":
    main()
