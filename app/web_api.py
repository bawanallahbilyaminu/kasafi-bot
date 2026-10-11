"""HTTP API used by the Kasafi web app's server (web/server). Browsers never call this directly.

Auth: header `x-api-key: <ENGINE_API_KEY>`. Mounted on the same FastAPI app (port 8080) as the WhatsApp webhook,
so one tunnel exposes both.

  POST /api/ask       JSON {user_id, text, name, organization}          -> text/event-stream
  POST /api/voice     multipart {audio, user_id, name, organization}    -> text/event-stream
  POST /api/speak     JSON {interaction_id, text, lang}                 -> audio/mpeg (Hausa voice)
  POST /api/feedback  JSON {interaction_id, value}
  GET  /api/health

The stream sends `event: stage` ({stage: understand|search|write|heard, text?}) while the engine works, then one
`event: answer` ({text, interaction_id, transcript, lang, input_type, voice}) or `event: error`.
"""
import json
import logging
import queue
import threading

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import config
from .engine import Reply
from .logstore import user_hash

log = logging.getLogger("natlas.web_api")
router = APIRouter(prefix="/api")
ENGINE = None   # set by run_all / the host app


class AskIn(BaseModel):
    user_id: str
    text: str
    name: str = ""
    organization: str = ""


class SpeakIn(BaseModel):
    interaction_id: int
    text: str
    lang: str = "ha"


class FeedbackIn(BaseModel):
    interaction_id: int
    value: int


def _auth(key):
    if not config.ENGINE_API_KEY:
        raise HTTPException(503, "ENGINE_API_KEY is not set on the engine")
    if key != config.ENGINE_API_KEY:
        raise HTTPException(401, "bad api key")
    if ENGINE is None:
        raise HTTPException(503, "engine is still loading")


def _register(uid, name, org):
    """Web users register in the web app; mirror name + organisation into the engine's users table."""
    if name:
        uh = user_hash("web", uid)
        first = not ENGINE.onboarding.profile(uh)
        ENGINE.logs.upsert_user(uh, channel="web", name=name.strip()[:60],
                                organization=(org or "None").strip()[:120], stage="done", completed=first)


def _stream(run):
    q = queue.Queue()

    def progress(stage, **info):
        q.put(("stage", {"stage": stage, **info}))

    def work():
        try:
            r = run(progress)
            q.put(("answer", {"text": r.text, "interaction_id": r.interaction_id, "transcript": r.transcript,
                              "lang": r.lang, "input_type": r.input_type, "voice": bool(ENGINE.tts) and r.lang == "ha"}))
        except Exception:  # noqa: BLE001
            log.exception("web request failed")
            q.put(("error", {"message": "The engine could not answer. Try again in a moment."}))
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def events():
        while True:
            try:
                item = q.get(timeout=10)
            except queue.Empty:
                yield ": ping\n\n"          # keeps tunnels and proxies from closing an idle stream
                continue
            if item is None:
                return
            ev, data = item
            yield f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ask")
def ask(body: AskIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    text = body.text.strip()[:1000]
    if not text:
        raise HTTPException(400, "empty question")
    _register(body.user_id, body.name, body.organization)
    return _stream(lambda progress: ENGINE.handle_text("web", body.user_id, text, progress=progress))


@router.post("/voice")
def voice(audio: UploadFile = File(...), user_id: str = Form(...), name: str = Form(""), organization: str = Form(""),
          x_api_key: str = Header(None)):
    _auth(x_api_key)
    data = audio.file.read()
    if not data or len(data) > 8_000_000:
        raise HTTPException(400, "voice note missing or too large")
    ctype = audio.content_type or ""
    suffix = ".webm" if "webm" in ctype else ".m4a" if ("mp4" in ctype or "aac" in ctype) else ".ogg" if "ogg" in ctype \
        else ".wav" if "wav" in ctype else ".webm"
    _register(user_id, name, organization)
    return _stream(lambda progress: ENGINE.handle_voice("web", user_id, data, suffix, progress=progress))


@router.post("/speak")
def speak(body: SpeakIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    if not ENGINE.tts:
        raise HTTPException(503, "voice replies are turned off")
    audio = ENGINE.speak(Reply(body.text, body.interaction_id, lang=body.lang), fmt="mp3")   # mp3 plays in every browser
    if not audio:
        raise HTTPException(500, "voice reply failed")
    return Response(audio, media_type="audio/mpeg")


@router.post("/feedback")
def feedback(body: FeedbackIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    ENGINE.feedback(body.interaction_id, 1 if body.value > 0 else -1)
    return {"ok": True}


# ---------------------------------------------------------------- admin (the web server checks the admin's identity)
class ReviewIn(BaseModel):
    status: str = ""      # "" | ok | issue | fixed
    note: str = ""


@router.get("/admin/stats")
def admin_stats(x_api_key: str = Header(None)):
    _auth(x_api_key)
    return ENGINE.logs.admin_stats()


@router.get("/admin/interactions")
def admin_interactions(channel: str = "", view: str = "all", q: str = "", limit: int = 50, offset: int = 0,
                       x_api_key: str = Header(None)):
    _auth(x_api_key)
    return ENGINE.logs.admin_list(channel or None, view, q.strip() or None, min(max(limit, 1), 200), max(offset, 0))


@router.get("/admin/interactions/{iid}")
def admin_interaction(iid: int, x_api_key: str = Header(None)):
    _auth(x_api_key)
    row = ENGINE.logs.admin_get(iid)
    if not row:
        raise HTTPException(404, "interaction not found")
    for k in ("facts", "entities", "natlas_understanding"):
        try:
            row[k] = json.loads(row[k]) if row.get(k) and k != "facts" else row.get(k)
        except (TypeError, ValueError):
            pass
    return row


@router.post("/admin/interactions/{iid}/review")
def admin_review(iid: int, body: ReviewIn, x_api_key: str = Header(None)):
    _auth(x_api_key)
    if body.status not in ("", "ok", "issue", "fixed"):
        raise HTTPException(400, "status must be ok, issue or fixed")
    if not ENGINE.logs.admin_review(iid, body.status, body.note):
        raise HTTPException(404, "interaction not found")
    return ENGINE.logs.admin_get(iid)


@router.get("/health")
def health():
    return {"ok": ENGINE is not None, "asr": bool(ENGINE and ENGINE.asr), "llm": bool(ENGINE and ENGINE.llm),
            "tts": bool(ENGINE and ENGINE.tts)}
