"""Settings, read from environment variables / a .env file next to the project."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(name, default=None):
    return os.environ.get(name, default)


BUDGET_DB = Path(env("BUDGET_DB", ROOT / "data" / "db" / "budget.sqlite"))
LOG_DB = Path(env("LOG_DB", ROOT / "data" / "db" / "interactions.sqlite"))

# --- N-ATLaS (LLM) ---
# LLM_BACKEND: "transformers" (run locally on the GPU), "openai" (any OpenAI-compatible server
# serving N-ATLaS, e.g. vLLM on Colab or llama.cpp), or "none" (template answers only, for testing)
LLM_BACKEND = env("LLM_BACKEND", "transformers")
NATLAS_MODEL = env("NATLAS_MODEL", "NCAIR1/N-ATLaS")
LLM_4BIT = env("LLM_4BIT", "1") == "1"
OPENAI_BASE_URL = env("OPENAI_BASE_URL", "http://localhost:8000/v1")
OPENAI_API_KEY = env("OPENAI_API_KEY", "not-needed")
OPENAI_MODEL = env("OPENAI_MODEL", "NCAIR1/N-ATLaS")

# --- Hausa ASR ---
ASR_MODEL = env("ASR_MODEL", "NCAIR1/Hausa-ASR")
ASR_ENABLED = env("ASR_ENABLED", "1") == "1"

# --- Hausa voice replies (TTS) ---
TTS_MODEL = env("TTS_MODEL", "facebook/mms-tts-hau")
TTS_RATE = float(env("TTS_RATE", "0.9"))
TTS_ENABLED = env("TTS_ENABLED", "1") == "1"
VOICE_REPLY = env("VOICE_REPLY", "voice")   # voice = reply with a voice note when the user sent one | always | never

HF_TOKEN = env("HF_TOKEN")

# --- Channels ---
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = env("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox number
# Public https URL of this server (the cloudflared tunnel), needed to send voice notes on WhatsApp
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "").rstrip("/")
MEDIA_DIR = Path(env("MEDIA_DIR", ROOT / "data" / "media"))

# Salt for hashing user ids in the interaction log (never store raw phone numbers / ids)
LOG_SALT = env("LOG_SALT", "change-me")

BUDGET_TITLE_HA = "Kasafin Kudin Jihar Sokoto na 2026 (wanda aka amince)"
BUDGET_TITLE_EN = "Sokoto State 2026 Approved Budget"

ATTRIBUTION = ("N-ATLaS and Hausa-ASR are powered by Awarri Technologies in an initiative of the Federal Ministry "
               "of Communications, Innovation and Digital Economy.")
