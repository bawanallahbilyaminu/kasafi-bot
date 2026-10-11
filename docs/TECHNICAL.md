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
 │  9. Optional voice reply: the finished answer is read aloud in Hausa     │
 │     by facebook/mms-tts-hau (no understanding or writing; TTS_ENABLED)   │
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

**N-ATLaS does all question understanding and answer writing.** Voice input uses the official
`NCAIR1/Hausa-ASR`.
- **No other language model:** none is used for understanding or writing. The `openai` backend in `llm.py`
  exists only to call **N-ATLaS** when it is served by vLLM on Colab (backup hosting).
- **Keyword rules** (`nlu.py`) help match official ministry and LGA names.
- **Template fallback:** if an N-ATLaS draft fails the grounding check (section 6), a fixed template with the
  verified figures is sent instead. Neither the rules nor the template involve a model.

**Text-to-speech (voice replies only).** N-ATLaS has no text-to-speech model.
- **What it does:** `facebook/mms-tts-hau` (Meta MMS-TTS Hausa) only reads out N-ATLaS's finished answer as a Hausa
  voice note, for users who cannot read (section 5c). It does no understanding or writing, and adds nothing to
  the content of an answer.
- **Switching it off:** set `TTS_ENABLED=0`. Text answers are unchanged.
- **Future:** it will be replaced by an official N-ATLaS voice when one is released.

| Component | Model | Where in code | Role |
|---|---|---|---|
| Voice replies (optional) | `facebook/mms-tts-hau` (VITS, ~36M) — not an N-ATLaS asset | `app/tts.py` → `HausaTTS.speak` | Reads the finished answer aloud in Hausa |
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

### 5a. 2025 Approved Budget
The same parsers, which now read each document's column layout and years from its header rows, load the 2025
approved budget into `line_items_2025` (2,117 rows) and `projects_2025` (1,695 projects).
`validate.py --year 2025` runs **3,504 checks, all passing**, apart from two **documented source discrepancies**:
the 2025 budget prints the Water Board's 2024 January–September capital performance as ₦671,280,010.00, but its
project lines sum to ₦671,280,000.00. That ₦10 difference is inside the document itself.

What it adds:
- the **original 2025 budget**, before the mid-year revision (e.g. Education ₦59.59bn → ₦57.2bn final)
- **2023 actuals** and **2024 January–September spending**, for multi-year trends

Data-quality finding: the 2026 budget's "2024 Full Year Actuals" column totals only ₦67.5bn, while the 2025
budget reports ₦166.8bn already spent by September 2024. The 2026 document's 2024 column is incomplete, so the
bot takes 2024 figures from the 2025 budget instead.

### 5b. Quarterly Budget Implementation Reports (2025 Q2–Q4, 2026 Q2)
`pipeline/parse_reports.py` loads the quarterly implementation reports into `perf_items` (7,548 rows): for every
administrative, economic, functional and programme line it records the original budget, revised/final budget, the
quarter's spending, year-to-date spending, % performance and balance. Q1 reports are kept as source documents;
their year-to-date figures are contained in Q2.

`pipeline/validate_reports.py`: **4,567 checks, all passing**
- MDAs → ministries → sectors → total, for total, personnel, overhead, other and capital, in every report
- personnel + overhead + other + capital = total for every MDA
- functional, programme and economic totals equal the administrative total
- **cross-document:** the 2025 Q3 report's year-to-date spending equals the "2025 January–September" column of
  the 2026 budget (₦227,654,787,906.93), for total, personnel, capital and overhead + other recurrent
- 11 MDA totals differ between the two documents because the 2026 budget re-filed some 2025 figures under other
  MDAs. These are counted and reported, not hidden.

How the bot uses them:
- 2025 questions are answered with **full-year 2025** figures (Q4 report).
- Every allocation answer also shows **2026 spending so far** (latest 2026 report, currently January–June).
- Revenue answers show amounts actually received.
- Project-level 2025 figures still come from the 2026 budget (January–September), because the reports list
  projects only for primary health care and basic education.

## 5c. Hausa voice replies
When a user sends a voice note (or turns on `/murya`), the bot also replies with a **Hausa voice note**. The
headline of the answer is converted to speakable Hausa by `app/speak.py`:
- numbers and naira amounts become Hausa words, in whatever order the answer writes them ("₦8.75 biliyan",
  "Naira biliyan 8.75", "biliyan 8.75", "8.75bn" all → "naira biliyan takwas da miliyan ɗari bakwai da hamsin");
  "kashi 10.6 cikin 100" → "kashi goma ɗigo shida cikin ɗari"
- text is lowercased and common words get their standard spelling with hooked letters (ɗari, huɗu, kuɗi, ƙaramar…),
  because the MMS Hausa voice was trained on standard orthography and its alphabet has no capitals, digits or
  punctuation
- pauses are inserted by code at every comma and full stop; speaking rate 0.9 (`TTS_RATE`) for clearer figures
- markdown and sources are removed

The text is then synthesised by **Meta MMS-TTS Hausa** (`facebook/mms-tts-hau`, VITS, CC-BY-NC 4.0) and encoded as
OGG/Opus.
- **Why it exists:** N-ATLaS has no text-to-speech model. This component only reads out the finished answer, which
  N-ATLaS wrote from the database facts. The purpose is accessibility for citizens who cannot read.
- **What it doesn't do:** no understanding, answer writing or figures come from it. The text it reads has already
  passed the grounding check.
- **Switching it off:** set `TTS_ENABLED=0`. The bot then answers in text only, with no other change.
- **Future:** it will be replaced by an official N-ATLaS voice when one is released.
- **WhatsApp:** voice notes are served from `/media/` on the bot's public tunnel URL.
- **Logging:** voice replies are logged (`voice_reply`, `ms_tts`).

## 6. Answer safety (grounding)
- The model never sees the database. It sees only a short list of facts, each already formatted
  (for example `₦124.41 biliyan`).
- **Year focus:** when a question is about a past year only (e.g. "how much was spent in 2025"), N-ATLaS receives
  only that year's facts. The 2026 breakdown and projects are added under its answer by code, labelled "(2026)".
  This closed a real failure found in testing: a 2025 social-protection question was answered with a 2026
  sub-category allocation (₦8.75bn) instead of the ₦16.22bn spent in 2025. The number existed in the facts, so the
  number check alone passed it. `tests/test_questions.py` now checks this case.
- Every project, agency and category line given to N-ATLaS carries its year ("Rabe (kasafin 2026): …").
- `answer.grounded()` extracts every number from the draft. If any number isn't in the facts, the draft is
  rejected and logged (`grounding_fail`), and the template answer is sent.
- Page citations are added by code, not by the model.
- Each answer is labelled with what the figure is (approved 2026, revised 2025, or actual January–September
  2025), so allocation is never presented as spending.

## 7. Privacy
- User ids (Telegram id or WhatsApp number) are stored only as a salted SHA-256 hash.
- Users' audio is transcribed in memory and not stored.
- The bot's own WhatsApp voice replies are saved in `data/media/`, so Twilio can fetch them. They contain only the
  spoken answer, never user audio.
- The bot only answers about public budget documents.

## 8. Licensing
- Hausa-ASR's terms allow civic-technology use for up to 1,000 monthly active users, with attribution
  (shown in the bot's /start, /about and this document).
- Wider deployment would need the commercial licence from Awarri and FMCIDE.
- `facebook/mms-tts-hau` (voice replies) is licensed CC-BY-NC 4.0 (non-commercial). It is used here for a free
  civic service and can be switched off with `TTS_ENABLED=0`; it will be replaced by an official N-ATLaS voice
  when one is released.

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
