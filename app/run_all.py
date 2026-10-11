"""Run Telegram + WhatsApp together in ONE process so the models load once (8 GB GPU).

Run:  python -m app.run_all            (Telegram + WhatsApp webhook on port 8080)
      python -m app.run_all --no-whatsapp
"""
import argparse
import logging
import threading

from . import config
from . import telegram_bot, whatsapp_twilio
from .engine import Engine

log = logging.getLogger("natlas.run_all")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-whatsapp", action="store_true")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    engine = Engine()
    telegram_bot.ENGINE = engine
    whatsapp_twilio.ENGINE = engine
    if not args.no_whatsapp and config.TWILIO_ACCOUNT_SID:
        import uvicorn
        t = threading.Thread(target=uvicorn.run, args=(whatsapp_twilio.app,),
                             kwargs={"host": "0.0.0.0", "port": args.port, "log_level": "info"}, daemon=True)
        t.start()
        log.info("WhatsApp webhook listening on http://localhost:%d/whatsapp", args.port)
    elif not args.no_whatsapp:
        log.warning("TWILIO_* not set: WhatsApp disabled")
    telegram_bot.run(engine)


if __name__ == "__main__":
    main()
