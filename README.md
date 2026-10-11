# Kasafi Bot — Hausa voice assistant for the Sokoto State budget

Kasafi Bot answers citizens' questions about the **Sokoto State 2026 Approved Budget** and **2025 budget
performance** on Telegram and WhatsApp. People can type or send a **Hausa voice note**. Every answer is built
from figures extracted from the official budget document and ends with the page numbers it came from.

- **Language:** `NCAIR1/N-ATLaS` (Llama-3 8B, Hausa/Yoruba/Igbo/English) does all question understanding and
  answer writing. It turns the question into English plus topic hints, and writes the answer in Hausa or English
  using only the retrieved facts. N-ATLaS is the only language model in the bot. (Keyword rules help match official
  ministry and LGA names. If an N-ATLaS draft fails the number check below, the verified figures are sent as a
  fixed template instead. Neither uses another model.)
- **Voice input:** every voice note is transcribed by the official N-ATLaS speech model, `NCAIR1/Hausa-ASR`
  (Whisper-small).
- **Voice replies:** N-ATLaS has no text-to-speech model. For users who cannot read, `facebook/mms-tts-hau`
  (Meta MMS-TTS Hausa) **only reads out N-ATLaS's finished answer** as a Hausa voice note. It does no
  understanding or writing. It can be switched off with `TTS_ENABLED=0` and will be replaced by an official
  N-ATLaS voice when one is released.
- **Data:** 9,049 budget lines and 1,710 capital projects, extracted from the 231-page budget PDF and checked
  against the document's own totals (3,719 checks pass).
- **Grounding guard:** every number in an N-ATLaS answer must appear in the retrieved facts. If any doesn't,
  the bot sends the verified figures instead.

Built by Halal Numeriq Limited (HNQ), Sokoto, for the National AI Innovation Challenge 2026
(Problem Statement 2: Voice-First Access).

> N-ATLaS and Hausa-ASR are powered by Awarri Technologies in an initiative of the Federal Ministry of
> Communications, Innovation and Digital Economy.

---

## 1. Setup on Windows (Acer Nitro V 15, RTX 4060 8 GB)

Open **Anaconda Prompt** in the project folder (for example `C:\kasafi-bot`).

```bat
conda create -n kasafi python=3.11 -y
conda activate kasafi
pip install "torch>=2.6" --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Fill in `.env`:
- `HF_TOKEN`: accept the terms on https://huggingface.co/NCAIR1/N-ATLaS and https://huggingface.co/NCAIR1/Hausa-ASR
  first, then create a Read token.
- `TELEGRAM_BOT_TOKEN`: from @BotFather.
- `LOG_SALT`: any long random text.

Check everything works:

```bat
python -m tests.test_questions          :: speech 4/4 + 31/31 routing and figure checks (no GPU needed)
python scripts\check_models.py          :: loads N-ATLaS (4-bit) + Hausa-ASR + Hausa TTS, runs one Hausa round trip
python -m app.cli                       :: chat in the terminal
```

Expect about 6 GB of GPU memory for N-ATLaS in 4-bit plus about 1 GB for Hausa-ASR.

## 2. Run the bot

```bat
python -m app.run_all --no-whatsapp     :: Telegram only
python -m app.run_all                   :: Telegram + WhatsApp webhook on port 8080
```

Keep the laptop on mains power with sleep disabled (Settings → System → Power → Sleep: Never).

### Registration and admin commands
New users are asked for their **name** and **organisation** before the first answer (Telegram and WhatsApp). Their
first question is kept and answered right after. `/canza` updates the profile. Set `REQUIRE_REGISTRATION=0` to turn
this off.

Put your Telegram id in `.env` as `ADMIN_TELEGRAM_IDS` (send `/myid` to the bot to see it), then use:
`/stats` (totals, voice share, N-ATLaS rate, feedback, organisations), `/recent 10` (latest questions and answers
with who asked) and `/bad 10` (👎, template fallbacks and errors: check these first).

### What users see while the bot works (Telegram)
One status message updates live: "⏳ Ina sauraron sakon muryarka…" → "🎙️ Na ji: “…”" → "✅ Na fahimci tambayar" →
"⏳ Ina duba kasafin kudi…" → "⏳ Ina rubuta amsa (N-ATLaS)…". Telegram's "typing…" / "recording voice…" indicator
stays on throughout, and "🔊 Ina nadar amsa da murya…" shows while the voice reply is made. For voice notes the
status shrinks to the transcript at the end, so the user can check what was heard.

### Hausa voice replies
On by default (`TTS_ENABLED=1`). When someone sends a voice note, the bot answers with text **and** a Hausa voice
note, so people who cannot read can still hear the answer. On Telegram, `/murya` turns voice replies on for every
answer.

- **What reads it out:** N-ATLaS has no text-to-speech model, so `facebook/mms-tts-hau` (about 150 MB, downloaded
  automatically the first time) reads out the answer N-ATLaS has already written. It adds nothing to the content.
- **Switching it off:** set `TTS_ENABLED=0` in `.env`. Text answers are unaffected.
- **Future:** it will be replaced by an official N-ATLaS voice when one is released.

`scripts\check_models.py` saves a sample to `evidence\tts_sample.ogg`; listen to it to check.

### WhatsApp (Twilio Sandbox)
1. In the Twilio Console go to **Messaging → Try it out → Send a WhatsApp message**. Note the sandbox
   number and the join code.
2. Expose the webhook. Download `cloudflared.exe` from Cloudflare, then run:
   `cloudflared tunnel --url http://localhost:8080`
3. In **Sandbox settings → When a message comes in**, paste `https://<your-tunnel>.trycloudflare.com/whatsapp`
   and choose POST.
   For voice-note replies on WhatsApp, also put the tunnel address in `.env`: `PUBLIC_BASE_URL=https://<your-tunnel>.trycloudflare.com`
4. Testers send `join <code>` to the sandbox number once, then ask questions.

   Trial accounts are capped at 50 messages a day, so add credit to lift the cap. Testers must re-join every 3 days.

## 2b. Web app
A web version with sign-in (Google), chat history and voice is in `web/` (React + Express + Clerk). It calls this
engine's `/api` routes; see `web/README.md`.

## 3. Collect real-world validation (NAIC requires at least 50 interactions)

Every question is logged in `data/db/interactions.sqlite`. The log stores the time, channel, a salted hash of the
user id, the transcript, how the question was understood, the facts used, the answer, timings, which model wrote
it, and 👍/👎 feedback. **No phone numbers or names are stored.**

```bat
python scripts\export_evidence.py       :: writes evidence\interactions.csv + evidence\summary.md
```

## 4. Backup: run on Google Colab
If the laptop fails, upload the project zip to Google Drive and open `colab/kasafi_backup_colab.ipynb`
(L4 GPU). Stop the laptop bot first, because only one copy can poll a Telegram bot token. Merge logs afterwards
with `python scripts\merge_logs.py <colab_log.sqlite>`.

## 5. Rebuild the database (when the Excel files arrive or a new document is published)

```bat
python -I pipeline\parse_budget.py   data\raw\budget2026.pdf data\db\budget.sqlite
python -I pipeline\parse_projects.py data\raw\budget2026.pdf data\db\budget.sqlite 49 75
python -I pipeline\validate.py       data\db\budget.sqlite
:: 2025 approved budget (portrait layout; separate tables)
python -I pipeline\parse_budget.py   data\raw\budget2025.pdf data\db\budget.sqlite --year 2025 --table line_items_2025 --stop 29 --no-detail
python -I pipeline\parse_projects.py data\raw\budget2025.pdf data\db\budget.sqlite 30 48 --year 2025 --table projects_2025 --min-nums 3
python -I pipeline\validate.py       data\db\budget.sqlite --year 2025 --table line_items_2025 --projects projects_2025
:: quarterly implementation reports (add new ones as they are published)
python -I pipeline\parse_reports.py   data\db\budget.sqlite data\raw\perf2025q2.pdf data\raw\perf2025q3.pdf data\raw\perf2025q4.pdf data\raw\perf2026q2.pdf
python -I pipeline\validate_reports.py data\db\budget.sqlite
```

## Project layout
```
app/        engine.py (pipeline), nlu.py (Hausa/English understanding), retrieve.py (facts from SQLite),
            answer.py (templates, grounding check, citation), llm.py (N-ATLaS), asr.py (Hausa-ASR),
            logstore.py (evidence log), telegram_bot.py, whatsapp_twilio.py, run_all.py, cli.py
pipeline/   PDF → SQLite extraction + validation against printed totals
data/       raw/budget2026.pdf, db/budget.sqlite
scripts/    check_models.py, export_evidence.py, merge_logs.py
tests/      test_questions.py
docs/       TECHNICAL.md (architecture, N-ATLaS integration, data validation, limitations)
colab/      backup notebook
```
