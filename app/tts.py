"""Hausa text-to-speech for voice-note replies.

Model: facebook/mms-tts-hau (Meta MMS, VITS, ~150 MB, CC-BY-NC 4.0). N-ATLaS has no TTS model; this component
only reads out the answer N-ATLaS already wrote. Output: OGG/Opus bytes (what Telegram and WhatsApp play as a
voice note).
"""
import logging
import shutil
import subprocess
import threading
import time

import numpy as np

from . import config

log = logging.getLogger("natlas.tts")


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


ENCODE = {"ogg": ["-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg"],   # Telegram/WhatsApp voice note
          "mp3": ["-c:a", "libmp3lame", "-b:a", "48k", "-f", "mp3"]}                       # plays in every browser


def encode(audio: np.ndarray, sr: int, fmt="ogg") -> bytes:
    ff = _ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    out = subprocess.run([ff, "-nostdin", "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
                          *ENCODE[fmt], "-"], input=pcm, capture_output=True, check=True)
    return out.stdout


def to_ogg_opus(audio: np.ndarray, sr: int) -> bytes:
    return encode(audio, sr, "ogg")


class HausaTTS:
    def __init__(self):
        import torch
        from transformers import AutoTokenizer, VitsModel
        kw = {"token": config.HF_TOKEN} if config.HF_TOKEN else {}
        t0 = time.time()
        self.tok = AutoTokenizer.from_pretrained(config.TTS_MODEL, **kw)
        self.model = VitsModel.from_pretrained(config.TTS_MODEL, **kw)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device).eval()
        self.sr = self.model.config.sampling_rate
        # slightly slower than the default reads figures more clearly (TTS_RATE: 1.0 = model default, lower = slower)
        self.model.config.speaking_rate = config.TTS_RATE
        self._lock = threading.Lock()
        log.info("Hausa TTS loaded (%s) in %.1fs", config.TTS_MODEL, time.time() - t0)

    def _synth(self, text):
        import torch
        inputs = self.tok(text, return_tensors="pt").to(self.device)
        torch.manual_seed(0)                      # VITS samples durations; a fixed seed = the same voice every time
        with torch.no_grad():
            wav = self.model(**inputs).waveform[0].float().cpu().numpy()
        return wav

    def speak(self, text: str, fmt="ogg") -> bytes:
        """Hausa text (already verbalised) -> OGG/Opus voice note (or mp3 for browsers)."""
        import re
        # The model's alphabet has no punctuation, so pauses are made here: one phrase per comma / full stop.
        phrases = [p.strip() for p in re.split(r"(?<=[.,;!?])\s+", text) if p.strip()]
        merged = []
        for ph in phrases:                         # very short phrases sound clipped: join them to the next one
            if merged and len(merged[-1]) < 25 and not merged[-1].endswith((".", "?", "!")):
                merged[-1] = f"{merged[-1]} {ph}"
            else:
                merged.append(ph)
        pause = {"short": np.zeros(int(self.sr * 0.18), dtype=np.float32),
                 "long": np.zeros(int(self.sr * 0.4), dtype=np.float32)}
        with self._lock:
            parts = []
            for ph in merged:
                words = ph.rstrip(".,;!?")
                if not words:
                    continue
                parts += [self._synth(words), pause["long" if ph.endswith((".", "?", "!")) else "short"]]
        return encode(np.concatenate(parts), self.sr, fmt)
