"""N-ATLaS integration check: loads both official models and runs one Hausa round trip.

Use it (1) to confirm your setup works, (2) as integration evidence for NAIC (save the output).

  python scripts/check_models.py                    text only
  python scripts/check_models.py --audio test.ogg   also transcribe a Hausa voice note
"""
import argparse
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio")
    a = ap.parse_args()
    import torch
    import transformers
    print(f"python {platform.python_version()} | torch {torch.__version__} | transformers {transformers.__version__}")
    print(f"CUDA: {torch.cuda.is_available()}" + (f" ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else ""))
    from app import config
    from app.llm import NATLaS
    t = time.time()
    llm = NATLaS()
    print(f"\n[N-ATLaS] backend={llm.backend} model={llm.model_id} loaded in {time.time() - t:.1f}s")
    q = "Nawa aka ware wa ma'aikatar lafiya a kasafin 2026?"
    t = time.time()
    print("[understand]", llm.understand(q), f"({time.time() - t:.1f}s)")
    t = time.time()
    facts = "- Ma'aikatar Lafiya — kasafin 2026 da aka amince: ₦124.41 biliyan\n- Manyan ayyuka (2026): ₦104.64 biliyan"
    print("[write]", llm.write(q, facts, "ha"), f"({time.time() - t:.1f}s)")
    if a.audio:
        from app.asr import HausaASR
        t = time.time()
        asr = HausaASR()
        print(f"\n[Hausa-ASR] model={config.ASR_MODEL} loaded in {time.time() - t:.1f}s")
        t = time.time()
        text, secs = asr.transcribe(Path(a.audio).read_bytes(), Path(a.audio).suffix)
        print(f"[transcribe] {secs:.1f}s audio -> “{text}” ({time.time() - t:.1f}s)")
        # full voice -> answer round trip on the same transcript
        t = time.time()
        print("[understand transcript]", llm.understand(text), f"({time.time() - t:.1f}s)")
        from app.engine import Engine
        eng = Engine(load_models=False)
        eng.llm = llm
        r = eng.handle_text("check_models", "local", text, input_type="voice")
        print(f"[answer to transcript] ({time.time() - t:.1f}s)\n{r.text}")
    if config.TTS_ENABLED:
        from app.speak import to_speech
        from app.tts import HausaTTS
        t = time.time()
        tts = HausaTTS()
        print(f"\n[Hausa TTS] model={config.TTS_MODEL} loaded in {time.time() - t:.1f}s")
        sample = "An ware wa ma'aikatar lafiya ₦124.41 biliyan a kasafin 2026. Zuwa watan Yuni an kashe kashi 10.6 cikin 100."
        spoken = to_speech(sample)
        t = time.time()
        audio = tts.speak(spoken)
        out = ROOT / "evidence" / "tts_sample.ogg"
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(audio)
        print(f"[speak] “{spoken}” -> {out} ({len(audio) // 1024} KB, {time.time() - t:.1f}s)")
    if torch.cuda.is_available():
        print(f"\nGPU memory used: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
