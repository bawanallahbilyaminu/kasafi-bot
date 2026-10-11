"""Telegram channel for Kasafi Bot (long polling: no public URL needed).

Run:  python -m app.telegram_bot
"""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          filters)

from . import config
from .answer import HELP_EN, HELP_HA
from .engine import Engine
from .logstore import user_hash
from .onboarding import DONE  # noqa: F401  (re-exported for tests)

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("natlas.telegram")

ENGINE: Engine = None
EXAMPLES = ["Nawa aka ware wa lafiya a 2026?", "Nawa aka kashe a fannin ilimi a 2025?",
            "Wadanne ayyuka ne za a yi a Tambuwal?", "Nawa ne kudaden shigar jiha?"]
ABOUT = ("ℹ️ *Kasafi Bot* — Halal Numeriq Limited, Sokoto.\n"
         "Bayanai daga: Kasafin Kudin Jihar Sokoto na 2026 da na 2025 (wadanda aka amince), da rahotannin aiwatar da "
         "kasafi na kowane wata uku (2025–2026).\n"
         "Fasaha: N-ATLaS (harshe) da Hausa-ASR (murya).\n\n_" + config.ATTRIBUTION + "_\n\n"
         "Muna adana sunanku, kungiyarku, tambayoyinku da amsoshi domin inganta sabis. Ba ma adana lambar wayarku, "
         "kuma ba ma raba bayananku da kowa. Aiko /canza don sabunta sunanku ko kungiyarku.")


def feedback_kb(iid):
    return InlineKeyboardMarkup([[InlineKeyboardButton("👍 Ya taimaka", callback_data=f"fb:{iid}:1"),
                                  InlineKeyboardButton("👎 Bai taimaka ba", callback_data=f"fb:{iid}:-1")]])


def examples_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(q, callback_data=f"ex:{i}")] for i, q in enumerate(EXAMPLES)])


async def send_answer(update: Update, text: str, iid: int, transcript: str = None):
    msg = update.effective_message
    if transcript:
        await msg.reply_text(f"🎙️ Na ji: “{transcript}”")
    for i in range(0, len(text), 3900):  # Telegram limit 4096 chars
        chunk = text[i:i + 3900]
        last = i + 3900 >= len(text)
        try:
            await msg.reply_text(chunk, parse_mode=ParseMode.MARKDOWN, reply_markup=feedback_kb(iid) if last else None)
        except Exception:  # markdown parse errors on odd characters -> send plain
            await msg.reply_text(chunk, reply_markup=feedback_kb(iid) if last else None)

# ------------------------------------------------------------------ live progress
STEPS = {  # stage -> (Hausa in progress, Hausa done, English in progress, English done)
    "listen": ("Ina sauraron sakon muryarku", "Na saurari sakon", "Listening to your voice note", "Listened"),
    "understand": ("Ina fahimtar tambayar (N-ATLaS)", "Na fahimci tambayar", "Understanding the question (N-ATLaS)",
                   "Understood the question"),
    "search": ("Ina duba kasafin kudi", "Na duba kasafin kudi", "Searching the budget documents", "Searched the budget"),
    "write": ("Ina rubuta amsa (N-ATLaS)", "Na rubuta amsa", "Writing the answer (N-ATLaS)", "Answer written"),
}


class Status:
    """One message that updates as the engine works, plus Telegram's 'typing…' / 'recording voice…' indicator
    kept alive the whole time (Telegram clears a chat action after ~5 s, so it is re-sent every 4 s).

        ⏳ Ina sauraron sakon muryarku…          (voice received)
        🎙️ Na ji: “nawa aka kashe …”
        ✅ Na fahimci tambayar
        ⏳ Ina duba kasafin kudi…
    """

    def __init__(self, update: Update, lang="ha"):
        self.update, self.lang = update, lang
        self.loop = asyncio.get_running_loop()
        self.msg = None
        self.heard = None
        self.done_steps, self.current = [], None
        self.action = ChatAction.TYPING
        self._last = None
        self._ticker = None
        self._lock = asyncio.Lock()       # one edit at a time, in order
        self._pending = []                # updates sent from the worker thread
        self._closed = False

    async def start(self, stage):
        self._ticker = asyncio.create_task(self._keep_action())
        await self.set(stage)

    async def _keep_action(self):
        try:
            while True:
                try:
                    await self.update.effective_chat.send_action(self.action)
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    def _render(self):
        i = 0 if self.lang == "ha" else 2
        lines = []
        if self.heard:
            lines.append(f"🎙️ {'Na ji' if self.lang == 'ha' else 'I heard'}: “{self.heard}”")
        lines += [f"✅ {STEPS[s][i + 1]}" for s in self.done_steps if s != "listen"]
        if self.current:
            lines.append(f"⏳ {STEPS[self.current][i]}…")
        return "\n".join(lines)

    async def set(self, stage, text=None):
        async with self._lock:
            if not self._closed:
                await self._set(stage, text)

    async def _set(self, stage, text=None):
        if stage == "heard":
            self.heard = text
            if self.current == "listen":
                self.done_steps.append("listen")
            self.current = None
        elif stage in STEPS:
            if self.current and self.current != stage:
                self.done_steps.append(self.current)
            self.current = stage
        body = self._render()
        if not body or body == self._last:
            return
        self._last = body
        try:
            if self.msg is None:
                self.msg = await self.update.effective_message.reply_text(body)
            else:
                await self.msg.edit_text(body)
        except Exception:  # noqa: BLE001  (rate limit / "not modified": the answer matters, not the status)
            log.debug("status update failed", exc_info=True)

    def from_thread(self, stage, **info):
        """Progress callback for the engine, which runs in a worker thread."""
        self._pending.append(asyncio.run_coroutine_threadsafe(self.set(stage, info.get("text")), self.loop))

    async def finish(self):
        """Stop the indicator. Voice: the status shrinks to what was heard (so the user can check it).
        Text: the status is deleted."""
        if self._ticker:
            self._ticker.cancel()
        if self._pending:                 # let updates already sent from the worker thread land first
            await asyncio.gather(*(asyncio.wrap_future(f) for f in self._pending), return_exceptions=True)
        async with self._lock:
            self._closed = True
        try:
            if self.msg and self.heard:
                await self.msg.edit_text(f"🎙️ {'Na ji' if self.lang == 'ha' else 'I heard'}: “{self.heard}”")
            elif self.msg:
                await self.msg.delete()
        except Exception:  # noqa: BLE001
            pass


async def keep_action(chat, action, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await chat.send_action(action)
        except Exception:  # noqa: BLE001
            pass
        try:
            await asyncio.wait_for(stop.wait(), 4)
        except asyncio.TimeoutError:
            pass


# ------------------------------------------------------------------ registration (name + organisation)
def name_kb(user):
    full = " ".join(x for x in (user.first_name, user.last_name) if x)
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ {full}", callback_data="nm")]]) if full else None


async def reply_md(msg, text, kb=None):
    try:
        return await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception:  # noqa: BLE001
        return await msg.reply_text(text.replace("*", "").replace("_", ""), reply_markup=kb)


async def registered(update: Update, context: ContextTypes.DEFAULT_TYPE, text=None, voice=None):
    """True when the user can be answered. Otherwise runs one registration step and returns False.
    A question sent before registering (text or voice) is kept and answered when registration finishes."""
    if not config.REQUIRE_REGISTRATION:
        return True
    uh = user_hash("telegram", update.effective_user.id)
    if ENGINE.onboarding.profile(uh):
        return True
    pending = None
    if voice:
        context.user_data["pending_voice"] = voice
        pending = "voice"
    step = ENGINE.onboarding.step(uh, "telegram", text, pending=pending)
    msg = update.effective_message
    if not step.done:
        kb = name_kb(update.effective_user) if step.stage == "name" else None   # organisation: typed (UNDP, UNICEF…)
        await reply_md(msg, step.reply, kb)
        return False
    await reply_md(msg, step.reply, None if step.pending else examples_kb())
    if step.pending == "voice":
        v = context.user_data.pop("pending_voice", None)
        if v:
            await answer_voice(update, context, *v)
        else:
            await msg.reply_text("Don Allah ku sake aiko da sakon muryarku.")
    elif step.pending:
        await answer_text(update, context, step.pending)
    return False


async def canza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/canza: update name and organisation."""
    ENGINE.onboarding.restart(user_hash("telegram", update.effective_user.id), "telegram")
    await registered(update, context)


# ------------------------------------------------------------------ admin (ids in ADMIN_TELEGRAM_IDS)
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"Your Telegram id: {update.effective_user.id}")


def is_admin(update):
    return update.effective_user.id in config.ADMIN_TELEGRAM_IDS


async def send_long(msg, text):
    for i in range(0, len(text), 3900):
        await msg.reply_text(text[i:i + 3900])


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    s = ENGINE.logs.stats()
    n = s["interactions"] or 1
    orgs = "\n".join(f"  • {o}: {c}" for o, c in s["orgs"]) or "  —"
    await update.effective_message.reply_text(
        f"📊 Kasafi Bot\n"
        f"Interactions: {s['interactions']} (today {s['today']})  — target 50\n"
        f"Voice notes: {s['voice']} ({100 * s['voice'] // n}%)\n"
        f"Written by N-ATLaS: {s['natlas']} · template fallback: {s['template']}\n"
        f"Feedback: 👍 {s['thumbs_up']} · 👎 {s['thumbs_down']}\n"
        f"Registered users: {s['users']} (+{s['registering']} registering)\n"
        f"Organisations:\n{orgs}")


def fmt_rows(rows):
    out = []
    for (iid, ts, ch, typ, name, org, q, intent, src, gfail, fb, ans, err) in rows:
        mark = {1: " 👍", -1: " 👎"}.get(fb, "")
        a = (ans or "").split("📄")[0].strip().replace("\n", " ")
        out.append(f"#{iid} {ts[5:16].replace('T', ' ')} UTC · {ch} {'🎙️' if typ == 'voice' else '⌨️'} · {name} ({org}){mark}\n"
                   f"Q: {q or '—'}\n"
                   f"A [{src or '—'}{', ' + intent if intent else ''}]: {a[:220]}"
                   + (f"\n⚠️ {gfail}" if gfail else "") + (f"\n❌ {err}" if err else ""))
    return "\n\n".join(out) or "No interactions yet."


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/recent [n]: latest questions and answers, with who asked."""
    if not is_admin(update):
        return
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else 10
    await send_long(update.effective_message, fmt_rows(ENGINE.logs.recent(min(n, 30))))


async def bad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bad [n]: answers with 👎, template fallbacks or errors: the ones to check first."""
    if not is_admin(update):
        return
    n = int(context.args[0]) if context.args and context.args[0].isdigit() else 10
    await send_long(update.effective_message, fmt_rows(ENGINE.logs.recent(min(n, 30), only_bad=True)))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await registered(update, context, "/start"):
        return
    await update.effective_message.reply_text(HELP_HA + "\n\n_" + config.ATTRIBUTION + "_", parse_mode=ParseMode.MARKDOWN,
                                              reply_markup=examples_kb())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP_HA + "\n\n" + HELP_EN, parse_mode=ParseMode.MARKDOWN,
                                              reply_markup=examples_kb())


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ABOUT, parse_mode=ParseMode.MARKDOWN)


async def send_voice_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, reply):
    """Hausa voice note of the answer (when the user spoke, or chose /murya), with 'recording voice…' shown."""
    if not ENGINE.wants_voice(reply, context.user_data.get("voice")):
        return
    chat = update.effective_chat
    note = None
    try:
        note = await update.effective_message.reply_text("🔊 Ina nadar amsa da murya…")
    except Exception:  # noqa: BLE001
        pass
    stop = asyncio.Event()
    ticker = asyncio.create_task(keep_action(chat, ChatAction.RECORD_VOICE, stop))
    try:
        audio = await asyncio.to_thread(ENGINE.speak, reply)
    finally:
        stop.set()
        await ticker
    try:
        if audio:
            await chat.send_action(ChatAction.UPLOAD_VOICE)
            await update.effective_message.reply_voice(voice=audio, caption="🔊 Amsa da murya")
    finally:
        if note:
            try:
                await note.delete()
            except Exception:  # noqa: BLE001
                pass


async def murya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/murya toggles voice replies for every answer (default: only when you send a voice note)."""
    on = context.user_data.get("voice") != "always"
    context.user_data["voice"] = "always" if on else None
    await update.effective_message.reply_text(
        "🔊 Zan rika amsa ku da murya a kowace tambaya. (Aiko /murya don kashewa.)" if on else
        "🔇 Zan amsa da murya ne kawai idan kun aiko da sakon murya.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
    text = text or update.effective_message.text
    if await registered(update, context, text):
        await answer_text(update, context, text)


async def answer_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    uid = update.effective_user.id
    st = Status(update, ENGINE.nlu.detect_lang(text.lower()))
    await st.start("understand")
    try:
        reply = await asyncio.to_thread(ENGINE.handle_text, "telegram", uid, text, progress=st.from_thread)
    finally:
        await st.finish()
    await send_answer(update, reply.text, reply.interaction_id)
    await send_voice_reply(update, context, reply)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    media = msg.voice or msg.audio
    if media.duration and media.duration > 120:
        await msg.reply_text("Yi hakuri, a takaita sakon murya zuwa minti 2.")
        return
    f = await media.get_file()
    data = bytes(await f.download_as_bytearray())
    suffix = ".ogg" if msg.voice else "." + (media.mime_type or "audio/mpeg").split("/")[-1]
    if await registered(update, context, voice=(data, suffix)):
        await answer_voice(update, context, data, suffix)


async def answer_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, data: bytes, suffix: str):
    st = Status(update, "ha")
    await st.start("listen")
    try:
        reply = await asyncio.to_thread(ENGINE.handle_voice, "telegram", update.effective_user.id, data, suffix,
                                        progress=st.from_thread)
    finally:
        await st.finish()
    # the transcript stays visible in the status message, so it isn't repeated here
    await send_answer(update, reply.text, reply.interaction_id)
    await send_voice_reply(update, context, reply)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kind, *rest = q.data.split(":")
    if kind == "fb":
        iid, val = int(rest[0]), int(rest[1])
        ENGINE.feedback(iid, val)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text("Na gode da ra'ayinku! 🙏" if val > 0 else "Na gode. Za mu inganta. 🙏")
    elif kind == "ex":
        await on_text(update, context, text=EXAMPLES[int(rest[0])])
    elif kind == "nm":   # "use my Telegram name"
        await q.edit_message_reply_markup(reply_markup=None)
        u = update.effective_user
        await registered(update, context, " ".join(x for x in (u.first_name, u.last_name) if x))



def main():
    log.info("Loading models (N-ATLaS + Hausa-ASR)...")
    run(Engine())


def run(engine):
    global ENGINE
    ENGINE = engine
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["help", "taimako"], help_cmd))
    app.add_handler(CommandHandler(["about", "game"], about))
    app.add_handler(CommandHandler(["murya", "voice"], murya))
    app.add_handler(CommandHandler(["canza", "profile"], canza))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("bad", bad))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    log.info("Kasafi Bot is running on Telegram. Press Ctrl+C to stop.")
    # a fresh standard event loop for this thread (uvicorn in another thread may have changed the global policy)
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
