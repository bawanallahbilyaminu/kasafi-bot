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

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("natlas.telegram")

ENGINE: Engine = None
EXAMPLES = ["Nawa aka ware wa lafiya a 2026?", "Nawa aka kashe a fannin ilimi a 2025?",
            "Wadanne ayyuka ne za a yi a Tambuwal?", "Nawa ne kudaden shigar jiha?"]
ABOUT = ("ℹ️ *Kasafi Bot* — Halal Numeriq Limited, Sokoto.\n"
         "Bayanai daga: Kasafin Kudin Jihar Sokoto na 2026 (wanda aka amince), wanda ya kunshi abin da aka kashe a 2025.\n"
         "Fasaha: N-ATLaS (harshe) da Hausa-ASR (murya).\n\n_" + config.ATTRIBUTION + "_\n\n"
         "Ba mu adana lambar wayarku ko sunanku; muna adana tambaya da amsa kawai domin inganta sabis.")


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP_HA + "\n\n_" + config.ATTRIBUTION + "_", parse_mode=ParseMode.MARKDOWN,
                                              reply_markup=examples_kb())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP_HA + "\n\n" + HELP_EN, parse_mode=ParseMode.MARKDOWN,
                                              reply_markup=examples_kb())


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ABOUT, parse_mode=ParseMode.MARKDOWN)


async def send_voice_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, reply):
    """Hausa voice note of the answer (when the user spoke, or chose /murya)."""
    if not ENGINE.wants_voice(reply, context.user_data.get("voice")):
        return
    await update.effective_chat.send_action(ChatAction.RECORD_VOICE)
    audio = await asyncio.to_thread(ENGINE.speak, reply)
    if audio:
        await update.effective_message.reply_voice(voice=audio, caption="🔊 Amsa da murya")


async def murya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/murya toggles voice replies for every answer (default: only when you send a voice note)."""
    on = context.user_data.get("voice") != "always"
    context.user_data["voice"] = "always" if on else None
    await update.effective_message.reply_text(
        "🔊 Zan rika amsa ku da murya a kowace tambaya. (Aiko /murya don kashewa.)" if on else
        "🔇 Zan amsa da murya ne kawai idan kun aiko da sakon murya.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
    text = text or update.effective_message.text
    uid = update.effective_user.id
    await update.effective_chat.send_action(ChatAction.TYPING)
    reply = await asyncio.to_thread(ENGINE.handle_text, "telegram", uid, text)
    await send_answer(update, reply.text, reply.interaction_id)
    await send_voice_reply(update, context, reply)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    media = msg.voice or msg.audio
    if media.duration and media.duration > 120:
        await msg.reply_text("Yi hakuri, a takaita sakon murya zuwa minti 2.")
        return
    await update.effective_chat.send_action(ChatAction.TYPING)
    f = await media.get_file()
    data = bytes(await f.download_as_bytearray())
    suffix = ".ogg" if msg.voice else "." + (media.mime_type or "audio/mpeg").split("/")[-1]
    reply = await asyncio.to_thread(ENGINE.handle_voice, "telegram", update.effective_user.id, data, suffix)
    await send_answer(update, reply.text, reply.interaction_id, transcript=reply.transcript)
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
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    log.info("Kasafi Bot is running on Telegram. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
