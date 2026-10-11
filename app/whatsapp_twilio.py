"""WhatsApp channel via the Twilio WhatsApp Sandbox.

Twilio waits only ~15 s for a webhook reply and the models can take longer, so the webhook
returns immediately and the answer is sent afterwards through the Twilio REST API.

Run:   uvicorn app.whatsapp_twilio:app --port 8080
Then expose it (e.g. `cloudflared tunnel --url http://localhost:8080`) and paste
https://<tunnel>/whatsapp into Twilio Console > Messaging > Try it out > WhatsApp sandbox settings
("When a message comes in", method POST).
"""
import logging
import threading
import uuid

import requests
from fastapi import FastAPI, Form, HTTPException, Response
from fastapi.responses import FileResponse
from twilio.rest import Client

from . import config
from .answer import HELP_HA
from .engine import Engine
from .logstore import user_hash

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("natlas.whatsapp")

app = FastAPI(title="Kasafi Bot – WhatsApp")
ENGINE = None
TWILIO = None
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
FEEDBACK_HINT = "\n\nAmsar ta taimaka? Aiko da 👍 ko 👎"
POSITIVE = {"👍", "1", "eh", "yes", "ya taimaka", "na gode"}
NEGATIVE = {"👎", "0", "a'a", "no", "bai taimaka ba"}


@app.on_event("startup")
def _startup():
    global ENGINE, TWILIO
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
        raise RuntimeError("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
    TWILIO = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    if ENGINE is None:  # run_all.py injects a shared engine
        ENGINE = Engine()


def send(to, text):
    # WhatsApp messages are limited to 1600 characters through Twilio
    for i in range(0, len(text), 1500):
        TWILIO.messages.create(from_=config.TWILIO_WHATSAPP_FROM, to=to, body=text[i:i + 1500])


def send_voice(to, reply):
    """WhatsApp voice note: Twilio fetches the audio from PUBLIC_BASE_URL/media/<file>.ogg."""
    if not config.PUBLIC_BASE_URL or not ENGINE.wants_voice(reply):
        return
    audio = ENGINE.speak(reply)
    if not audio:
        return
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.ogg"
    (config.MEDIA_DIR / name).write_bytes(audio)
    TWILIO.messages.create(from_=config.TWILIO_WHATSAPP_FROM, to=to, media_url=[f"{config.PUBLIC_BASE_URL}/media/{name}"])


def process(sender, body, media_url, media_type):
    try:
        if media_url:
            audio = requests.get(media_url, auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN), timeout=60).content
            suffix = ".ogg" if "ogg" in (media_type or "") else "." + (media_type or "audio/ogg").split("/")[-1]
            reply = ENGINE.handle_voice("whatsapp", sender, audio, suffix)
            if reply.transcript:
                send(sender, f"🎙️ Na ji: “{reply.transcript}”")
        else:
            reply = ENGINE.handle_text("whatsapp", sender, body)
        send(sender, reply.text + FEEDBACK_HINT)
        send_voice(sender, reply)
    except Exception:  # noqa: BLE001
        log.exception("processing failed")
        send(sender, "Yi hakuri, an samu matsala. Don Allah a sake gwadawa.")


@app.post("/whatsapp")
def whatsapp(From: str = Form(...), Body: str = Form(""), NumMedia: int = Form(0),
             MediaUrl0: str = Form(None), MediaContentType0: str = Form(None)):
    text = (Body or "").strip()
    low = text.lower()
    if not NumMedia and (low in POSITIVE or low in NEGATIVE):
        iid = ENGINE.logs.last_for_user(user_hash("whatsapp", From))
        if iid:
            ENGINE.feedback(iid, 1 if low in POSITIVE else -1)
            threading.Thread(target=send, args=(From, "Na gode da ra'ayinku! 🙏"), daemon=True).start()
        return Response(EMPTY_TWIML, media_type="application/xml")
    if not NumMedia and low in {"join", "start", "/start", "help", "taimako", "menu"}:
        threading.Thread(target=send, args=(From, HELP_HA + "\n\n_" + config.ATTRIBUTION + "_"), daemon=True).start()
        return Response(EMPTY_TWIML, media_type="application/xml")
    media = MediaUrl0 if NumMedia and (MediaContentType0 or "").startswith("audio") else None
    threading.Thread(target=process, args=(From, text, media, MediaContentType0), daemon=True).start()
    return Response(EMPTY_TWIML, media_type="application/xml")


@app.get("/media/{name}")
def media(name: str):
    if not name.endswith(".ogg") or "/" in name or ".." in name:
        raise HTTPException(404)
    path = config.MEDIA_DIR / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/ogg")


@app.get("/health")
def health():
    return {"ok": True}
