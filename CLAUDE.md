# CLAUDE.md: Kasafi Bot (NAIC 2026 entry)

Handoff notes for Claude Code. Read this first.

## What this is
A Hausa voice-first WhatsApp/Telegram bot that answers citizens' questions about the **Sokoto State 2026
Approved Budget** and **2025 budget performance**, with exact figures and page citations. It is built by
Bilyaminu Bawan Allah / Halal Numeriq Limited (HNQ) for the **National AI Innovation Challenge (NAIC) 2026**,
Problem Statement 2 (Voice-First Access), Innovation & Enterprise track.

**DEADLINE: Monday 12 October 2026, 11:59 PM WAT. Target submission by 8 PM.** Official page:
https://ncair.nitda.gov.ng/naic/

Hard requirements from the challenge:
- a working build that genuinely integrates N-ATLaS
- voice input must use the official N-ATLaS ASR (`NCAIR1/Hausa-ASR`)
- **at least 50 documented real user interactions**
- a 3–5 minute demo video
- technical docs and a team profile (2–5 members)
- CAC certificate

Wrapping any other foundation model means disqualification.

## Machine
- Windows laptop: Acer Nitro V 15, RTX 4060 8 GB, 16 GB RAM. Anaconda.
- The user's existing `hf-env` has transformers 5.x (used for a course). **Do not install this project into
  hf-env.** Use a separate env: `conda create -n kasafi python=3.11`, then the CUDA torch wheel, then
  `pip install -r requirements.txt`, which pins transformers 4.x for bitsandbytes 4-bit on Windows.
- `huggingface_hub` 2.x removed `huggingface-cli`; use `hf auth login` / `hf download`. In hf-env the user
  had to downgrade to `huggingface_hub>=1.5,<2.0`. Model files live in the shared HF cache, so any env can use them.
- ffmpeg is required for voice notes. It comes from the `imageio-ffmpeg` pip package (in requirements.txt).
  Do not rely on conda-forge ffmpeg in the kasafi env: it crashes with 0xC0000139 because the env mixes
  defaults and conda-forge DLLs.
- torch must be >= 2.6 (`--index-url https://download.pytorch.org/whl/cu124`): Hausa-ASR ships
  `pytorch_model.bin`, which transformers 4.57 refuses to load on older torch (CVE-2025-32434).

## Architecture (see docs/TECHNICAL.md)
voice/text → `app/asr.py` (Hausa-ASR) → `app/llm.py` N-ATLaS `understand()` (Hausa→English + topic JSON) →
`app/nlu.py` (rules: Hausa/English lexicons, LGA names, official MDA names) → `app/retrieve.py` (SQLite facts
with page numbers) → N-ATLaS `write()` (answer from facts only) → `app/answer.py` `grounded()` (every number in
the draft must exist in the facts, else template answer) → citation appended by code → `app/logstore.py`
(interaction log = NAIC evidence).

`app/run_all.py` runs Telegram and WhatsApp (Twilio sandbox, FastAPI on :8080) in ONE process so the models
load once and fit in 8 GB.

## Data
- `data/raw/budget2026.pdf`: the 231-page approved budget (Excel-exported, text-based). It includes 2024
  actuals, 2025 revised, 2025 Jan–Sep actual performance, 2026 approved, and 2027/2028 estimates.
- `data/db/budget.sqlite`:
  - `line_items`: 9,049 rows; `kind` is one of exp_admin/exp_economic/exp_function/exp_location/
    exp_programme/revenue_*/mda_*_economic/basic_edu_*/phc_*; `measure` is total/personnel/overhead/
    debt_service/capital
  - `projects`: 1,710 capital projects with LGA
  - `projects_fts`: FTS5 search index over projects
- `pipeline/validate.py` must stay at **3,719/3,719 checks passing**. Run it after any parser change.
- The Excel versions of the budget and the performance reports are coming from MBEP. When they arrive, load
  them into the same tables (same schema) and re-run validate.

## Status (as of Sun 11 Oct, 13:00 WAT)
Done and verified (in a cloud workspace with no GPU and no pip access):
- extraction and validation: 3,719/3,719 checks pass
- engine logic with `LLM_BACKEND=none`: `python -m tests.test_questions` → 15/15
- grounding guard tested with a fake LLM (rejects invented numbers)
- all files compile

**NOT yet run anywhere:**
- the real N-ATLaS and Hausa-ASR models (`app/llm.py`, `app/asr.py`)
- python-telegram-bot
- FastAPI/Twilio

These are the first things to test on this laptop.

## Next steps (in order)
1. Create the GitHub repo and push. Suggested command:
   `gh repo create bawanallahbilyaminu/kasafi-bot --private --source=. --push`
   Make it public (or share with the judges) before submission.
2. User is downloading `NCAIR1/N-ATLaS` (~16 GB) and `NCAIR1/Hausa-ASR` via `hf download`.
3. Set up the `kasafi` env; `copy .env.example .env` (user fills HF_TOKEN, TELEGRAM_BOT_TOKEN, LOG_SALT,
   optional TWILIO_*).
4. `python scripts\check_models.py` (save the output to `evidence/check_models.txt` as integration evidence).
   Fix any loading or generation issues: chat template, 4-bit config, ASR `generate_kwargs` language hint.
5. Test with a real Hausa voice note: `python -m app.cli --audio note.ogg`.
6. Tune the N-ATLaS prompts in `app/llm.py` if answers fail the grounding check too often (look at the
   `grounding_fail` column in `data/db/interactions.sqlite`).
7. `python -m app.run_all --no-whatsapp` → live on Telegram. Then WhatsApp: Twilio sandbox + `cloudflared tunnel
   --url http://localhost:8080`, with the webhook at `/whatsapp`.
8. Recruit testers (message in `docs/SUBMISSION_CHECKLIST.md`). Need 50+ interactions, ideally half voice.
9. `python scripts\export_evidence.py` → `evidence/summary.md` + `interactions.csv`.
10. Demo video (script in the checklist), team profile, submit.

Backup hosting if the laptop fails: `colab/kasafi_backup_colab.ipynb` (L4 GPU).

## Known issues / to review
- **Hausa wording** in `app/answer.py` (HELP_HA, templates) and `app/retrieve.py` labels was written by an AI.
  The user is a native Hausa speaker and should review it.
- **Project names:** a few long project names bleed into the neighbouring project (PDF line wrapping).
  Amounts are correct. The Excel files will fix this.
- **Garbled names:** some 4-digit functional-classification names are garbled. Answers use admin/MDA tables,
  not these.
- **Capital receipts page** (grants/loans, page 14) is not parsed yet. It could be added like the projects table.
- **Licences:** the Hausa-ASR licence caps use at 1,000 monthly active users and requires attribution (already in
  /start, /about and the docs).

## Conventions
- Never commit `.env` or `data/db/interactions.sqlite` (both are gitignored; the log holds user data, even
  though ids are hashed).
- Before committing: `python -m tests.test_questions` and `python -I pipeline\validate.py data\db\budget.sqlite`.
- The model must never be the source of a number. Facts come from SQLite; N-ATLaS only phrases them.
