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

CASES = [  # question, expected text in the answer
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
    if e.nlu.parse("how many projects have been done for IDPs in Sokoto in 2025").intent != "project_status":
        print("FAIL claim: 'how many projects ... for IDPs' not routed to project status"); fails += 1
    if e.nlu.parse("o ana samun shi gaba ga ayyuka na social protection a jihar sokoto.").intent != "project_status":
        print("FAIL claim: ASR variant 'shi gaba' (ci gaba) not routed to project status"); fails += 1
    print(f"claims: {len(cases) + 3 - fails}/{len(cases) + 3} passed")
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
    speech_fails = speech_checks() + year_checks() + onboarding_checks() + claim_checks()
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
