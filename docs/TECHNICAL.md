# Kasafi Bot — Technical Documentation

**Team:** Halal Numeriq Limited (HNQ), Sokoto · **Challenge:** NAIC 2026, Problem Statement 2: Voice-First Access
· **Track:** Innovation & Enterprise

## 1. Problem
Sokoto State publishes its approved budget as a 231-page, table-heavy PDF in English. Most citizens speak
Hausa, many read little English, and few can work through classification tables. As a result, few people
can check what was allocated to their health centre, school or LGA, or how much of last year's budget
was actually spent.

## 2. Solution
Citizens ask in Hausa, by voice or text, on the apps they already use (Telegram and WhatsApp). Kasafi Bot answers with the exact
figures from the official document, explains them in simple Hausa, and cites the page numbers.

## 3. Architecture

```
 Telegram / WhatsApp (Twilio)
          │  voice note (OGG/Opus) or text
          ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ engine.py                                                                │
 │  1. ffmpeg → 16 kHz mono → NCAIR1/Hausa-ASR (N-ATLaS ASR)  → Hausa text  │
 │  2. N-ATLaS  understand(): Hausa → {english, topic, wants, year} (JSON)  │
 │  3. nlu.py: Hausa + English lexicons, LGA names, official MDA names      │
 │     → intent (mda / lga / project / revenue / overview) + entities       │
 │  4. retrieve.py: SQLite (9,049 budget lines, 1,710 projects, FTS5)       │
 │     → facts, each with value, year, measure and source page              │
 │  5. N-ATLaS  write(): Hausa/English answer from the facts only           │
 │  6. Grounding guard: every number in the draft must be in the facts,     │
 │     otherwise a deterministic template answer is sent instead            │
 │  7. Citation appended by code ("Madogara: … shafi 18, 27")               │
 │  8. logstore.py: interaction log (hashed user id) + 👍/👎 feedback        │
 └──────────────────────────────────────────────────────────────────────────┘
```

Telegram and WhatsApp share one engine in one process (`app/run_all.py`), so the models are loaded once.
That fits on an 8 GB laptop GPU (RTX 4060): N-ATLaS in 4-bit NF4 plus Hausa-ASR in fp16.

## 4. N-ATLaS integration (evidence)

| Component | Official N-ATLaS asset | Where in code | Role |
|---|---|---|---|
| Speech recognition | `NCAIR1/Hausa-ASR` (Whisper-small, 244M) | `app/asr.py` → `HausaASR.transcribe` | Every voice note is transcribed by the official Hausa ASR; 30 s chunking handles longer notes |
| Question understanding | `NCAIR1/N-ATLaS` (Llama-3 8B) | `app/llm.py` → `NATLaS.understand` | Few-shot prompt turns Hausa/Pidgin into an English rendering plus topic, intent and year (JSON) |
| Answer generation | `NCAIR1/N-ATLaS` | `app/llm.py` → `NATLaS.write` | Writes the citizen-facing answer in Hausa or English from retrieved facts only |

- No other foundation model is used. The `openai` backend in `llm.py` exists only to call **N-ATLaS** when it
  is served by vLLM on Colab (backup hosting).
- Each logged interaction records `asr_model` and `llm_model`, plus whether the final answer was written by
  N-ATLaS (`answer_source = natlas`) or replaced by the template after a failed grounding check.
- `scripts/check_models.py` loads both models and runs a Hausa round trip; its output is saved as setup evidence.

## 5. Data pipeline and validation
Source: *Sokoto State Government 2026 Approved Budget* (Excel-exported PDF, 231 pages). Besides the 2026
approved figures, each table also contains 2024 actuals, the 2025 revised budget, **2025 actual performance
(January–September)**, and estimates for 2027 and 2028.

| Table | Rows | Method |
|---|---|---|
| Expenditure by administrative unit (total / personnel / overhead / debt / capital) | 688 | word positions (pdfplumber) → column anchors |
| Expenditure by economic, functional, location, programme classification | ~1,050 | same |
| Revenue by administrative unit and by economic line | ~350 | same |
| Per-MDA economic detail (revenue and expenditure) | ~6,600 | same, with MDA context |
| Capital projects (name, MDA, economic, function, LGA, 6 year columns) | 1,710 | character-stream cell rebuild (cells overlap in the PDF), code-pattern splitting, nearest-row assignment |

`pipeline/validate.py` runs **3,719 checks, and all pass**:
- grand totals for total, personnel, overhead, debt service and capital match the Summary page for all 6 year columns
- MDAs → ministry → sector → total for every administrative table
- personnel + overhead + debt + capital = total for every MDA
- functional, location and programme tables add up to the same grand total
- all 1,710 projects reconcile with capital expenditure, per MDA and in total, to the kobo, for every year
- each MDA's economic-detail total matches its administrative total

PDF problems found and fixed during extraction:
- numbers split into fragments ("9,700,000 . 0 0")
- a digit glued to a name: resolved by reconciliation, keeping whichever reading balances the ministry totals
  (one name genuinely contains a footnote "1")
- letter-spaced names
- overlapping cells in the project table

## 6. Answer safety (grounding)
- The model never sees the database. It sees only a short list of facts, each already formatted
  (for example `₦124.41 biliyan`).
- `answer.grounded()` extracts every number from the draft. If any number isn't in the facts, the draft is
  rejected and logged (`grounding_fail`), and the template answer is sent.
- Page citations are added by code, not by the model.
- Each answer is labelled with what the figure is (approved 2026, revised 2025, or actual January–September
  2025), so allocation is never presented as spending.

## 7. Privacy
- User ids (Telegram id or WhatsApp number) are stored only as a salted SHA-256 hash.
- Audio is transcribed in memory and not stored.
- The bot only answers about public budget documents.

## 8. Licensing
- Hausa-ASR's terms allow civic-technology use for up to 1,000 monthly active users, with attribution
  (shown in the bot's /start, /about and this document).
- Wider deployment would need the commercial licence from Awarri and FMCIDE.

## 9. Known limitations
- **Project names:** wrapped project names are rebuilt from the PDF layout; 22 ambiguous wraps were repaired by
  a rule (a lowercase continuation line midway between two rows belongs to the project above). A few long names
  may still carry a stray fragment. Amounts are unaffected (they are reconciled), and the Excel files from MBEP
  will remove this issue. Note: the source document itself lists "Completion of Premier Hospital at Binji LGA"
  with location Tambuwal.
- **One unnamed project:** one IDP project row has no name in the source document; it is labelled
  "description missing".
- **"State Wide" projects:** 81% of projects by count are tagged "State Wide", so LGA answers show only
  projects located in that LGA and say so.
- **ASR accuracy** drops with background noise and Hausa–English code-switching (as the model card notes).
  The bot repeats back what it heard so the user can check.
- **Performance data** covers January–September 2025, the latest published in the 2026 budget. Quarterly
  performance reports will be added as separate documents.

## 10. Scalability and sustainability
- **New documents:** the parsers target the standard layout of Nigerian state budgets (administrative,
  economic, functional, programme and location classifications), so quarterly performance reports, the 2027
  budget, and budgets of other states in the same format can be loaded with the same pipeline and validated
  the same way.
- **Channels:** moving from the Twilio sandbox to a verified WhatsApp Business number lets anyone message the bot
  without a join code. USSD or IVR voice lines are the next step for feature phones.
- **Adoption:** built in Sokoto with knowledge of the Ministry of Budget and Economic Planning's processes. The
  goal is to host it as an official citizens' budget channel, fed directly from MBEP's Excel budget files.
- **Cost:** it runs on one consumer GPU. A small cloud GPU instance serves the expected traffic.
