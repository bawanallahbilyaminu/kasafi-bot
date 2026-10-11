"""Regression checks for question routing and grounded figures (no GPU needed).

Run: python -m tests.test_questions
"""
import os
import sys
import tempfile

os.environ["LLM_BACKEND"] = "none"
os.environ["ASR_ENABLED"] = "0"
os.environ["LOG_DB"] = os.path.join(tempfile.mkdtemp(), "test_log.sqlite")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine import Engine  # noqa: E402

CASES = [  # question, expected text in the answer
    ("Nawa aka ware wa lafiya a 2026?", "₦124.41 biliyan"),
    ("Nawa aka kashe a fannin ilimi a 2025?", "₦29.89 biliyan"),
    ("Wadanne ayyuka ne za a yi a Tambuwal?", "Karamar Hukumar Tambuwal"),
    ("Ayyukan rijiyoyin burtsatse nawa ne a kasafin?", "borehole"),
    ("Nawa ne kudaden shigar jiha?", "₦389.32 biliyan"),
    ("How much is allocated to agriculture in 2026?", "₦17.05 billion"),
    ("Nawa ne albashin ma'aikatar ilimi?", "₦12.12 biliyan"),
    ("Menene jimillar kasafin kudin 2026?", "₦758.7 biliyan"),
    ("How much did SUBEB spend in 2025?", "₦768.13 million"),
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
    ("Kasafin lafiya ya karu idan aka kwatanta da 2025?", "kashi 168.6"),
]


def main():
    e = Engine(load_models=False)
    fails = 0
    for q, want in CASES:
        a = e.handle_text("test", "t", q).text
        ok = want in a
        fails += not ok
        print(("PASS" if ok else "FAIL"), q, "" if ok else f"\n  expected '{want}' in:\n{a[:300]}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
