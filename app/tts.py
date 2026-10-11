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


def to_ogg_opus(audio: np.ndarray, sr: int) -> bytes:
    ff = _ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    out = subprocess.run([ff, "-nostdin", "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
                          "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg", "-"],
                         input=pcm, capture_output=True, check=True)
    return out.stdout


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
        self._lock = threading.Lock()
        log.info("Hausa TTS loaded (%s) in %.1fs", config.TTS_MODEL, time.time() - t0)

    def _synth(self, text):
        import torch
        inputs = self.tok(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            wav = self.model(**inputs).waveform[0].float().cpu().numpy()
        return wav

    def speak(self, text: str) -> bytes:
        """Hausa text (already verbalised) -> OGG/Opus voice note."""
        import re
        chunks, cur = [], ""
        for sent in re.split(r"(?<=[.,;])\s+", text):   # short chunks synthesise more reliably
            if len(cur) + len(sent) > 180 and cur:
                chunks.append(cur); cur = ""
            cur = (cur + " " + sent).strip()
        if cur:
            chunks.append(cur)
        gap = np.zeros(int(self.sr * 0.25), dtype=np.float32)
        with self._lock:
            parts = []
            for c in chunks:
                parts += [self._synth(c), gap]
        return to_ogg_opus(np.concatenate(parts), self.sr)
