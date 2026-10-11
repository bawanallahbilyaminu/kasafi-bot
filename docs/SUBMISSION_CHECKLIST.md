# NAIC 2026 submission checklist: Kasafi Bot

**Deadline: Monday 12 October 2026, 11:59 PM WAT.** Aim to submit by **8 PM** to leave a buffer.
Apply via the Innovation & Enterprise track: https://ondi.innox.africa/apply/naic/naic-innovation-enterprise
Problem statement: **02 Voice-First Access**

| # | Component | What to submit | Status |
|---|---|---|---|
| 1 | Working artefact | GitHub repo (private → share with judges, or public) + Telegram link `t.me/<your_bot>` + WhatsApp sandbox number & join code | ☐ |
| 2 | N-ATLaS integration evidence | `docs/TECHNICAL.md` §4 + output of `python scripts\check_models.py` (save as `evidence/check_models.txt`) + `llm_model`/`asr_model` columns in the log | ☐ |
| 3 | Real-world validation | `evidence/summary.md` + `evidence/interactions.csv` — **minimum 50 real interactions** | ☐ |
| 4 | Technical documentation | `README.md` (setup/usage) + `docs/TECHNICAL.md` (architecture, data validation) | ☐ |
| 5 | Video (3–5 min) | End-to-end demo, see script below | ☐ |
| 6 | Team profile | Names, affiliations, roles — **2–5 members** (track card says 2–5; FAQ says 1–6 — add at least one teammate to be safe) | ☐ |
| 7 | Registration | HNQ CAC certificate + valid ID | ☐ |

## Getting 50+ real interactions (tonight and tomorrow morning)
- Target 15–20 people × 3–4 questions each, with at least **half as voice notes** (it's the voice-first track).
- Mix of people: colleagues, family, students, people in your community who usually ask about the budget
  in Hausa.
- Ask everyone to press 👍/👎 after each answer.
- Check progress: `python scripts\export_evidence.py`

Tester message (edit as you like):

> Assalamu alaikum! Muna gwajin wata sabuwar manhaja mai suna **Kasafi Bot** da ke amsa tambayoyi game da
> Kasafin Kudin Jihar Sokoto na 2026 da yadda aka kashe kudin 2025 — cikin Hausa, har da sakon murya.
> Don Allah ku tura masa tambayoyi 3 zuwa 4 (ku yi amfani da sakon murya idan zai yiwu), sannan ku danna 👍 ko 👎.
> Telegram: t.me/<bot> · WhatsApp: tura "join <code>" zuwa +1 415 523 8886 sannan ku yi tambaya.
> Misali: "Nawa aka ware wa lafiya a 2026?" ko "Wadanne ayyuka ne za a yi a karamar hukumarmu?"

## Video script (about 4 minutes)
1. **0:00–0:30 Problem.** Show the 231-page PDF. "Most people in Sokoto speak Hausa; this document is in English
   tables."
2. **0:30–1:00 What it is.** "Kasafi Bot: ask in Hausa by voice on Telegram or WhatsApp, get exact figures with page
   numbers." Show the architecture diagram from TECHNICAL.md.
3. **1:00–2:45 Live demo** (phone screen recording):
   - voice note: "Nawa aka ware wa lafiya a 2026?" → transcript + answer with page citation
   - voice note: "Nawa aka kashe a fannin ilimi a 2025?" → implementation rate
   - text: "Wadanne ayyuka ne za a yi a Tambuwal?" → project list
   - open the PDF at the cited page to show the same figure
4. **2:45–3:30 N-ATLaS integration and grounding.** Terminal: `check_models.py` output. Show a grounding-guard
   example (a draft with an invented number gets rejected).
5. **3:30–4:00 Validation and next steps.** `evidence/summary.md` (number of interactions and users, voice
   share, feedback). Next: Excel feed from MBEP, quarterly performance reports, verified WhatsApp number,
   other states.
