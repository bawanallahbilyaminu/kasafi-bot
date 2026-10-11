"""Ask the bot from the terminal (no Telegram/WhatsApp needed).

  python -m app.cli                       interactive
  python -m app.cli "Nawa aka ware wa lafiya?"
  python -m app.cli --audio note.ogg      transcribe a voice note with Hausa-ASR and answer
  python -m app.cli --no-models "..."     rules + templates only (no GPU)
"""
import argparse
import os
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--audio")
    ap.add_argument("--no-models", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console (cp1252) cannot print the naira sign
    if a.no_models:
        os.environ["LLM_BACKEND"] = "none"
        os.environ["ASR_ENABLED"] = "0"
    from .engine import Engine
    e = Engine(load_models=not a.no_models)
    if a.audio:
        r = e.handle_voice("cli", "local", Path(a.audio).read_bytes(), Path(a.audio).suffix)
        print(f"[transcript] {r.transcript}\n\n{r.text}")
        return
    if a.question:
        print(e.handle_text("cli", "local", " ".join(a.question)).text)
        return
    while True:
        try:
            q = input("\nTambaya> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q:
            print("\n" + e.handle_text("cli", "local", q).text)


if __name__ == "__main__":
    main()
