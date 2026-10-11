"""Hausa speech recognition with NCAIR1/Hausa-ASR (official N-ATLaS ASR, Whisper-small).

Voice notes from Telegram / WhatsApp arrive as OGG/Opus; ffmpeg converts them to 16 kHz mono.
"""
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from . import config

log = logging.getLogger("natlas.asr")


def _ffmpeg_exe():
    # Prefer the self-contained imageio-ffmpeg binary: conda-forge ffmpeg can fail on Windows
    # (0xC0000139) when the env mixes defaults and conda-forge runtime DLLs.
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def decode_audio(data: bytes, suffix=".ogg"):
    """Return float32 mono 16 kHz samples from any audio container ffmpeg understands."""
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install it: pip install imageio-ffmpeg")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / f"in{suffix}"
        src.write_bytes(data)
        out = subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000",
                              "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(out.stdout, dtype=np.float32)


class HausaASR:
    def __init__(self):
        import torch
        from transformers import pipeline
        kw = {"token": config.HF_TOKEN} if config.HF_TOKEN else {}
        t0 = time.time()
        device = 0 if torch.cuda.is_available() else -1
        self.pipe = pipeline("automatic-speech-recognition", model=config.ASR_MODEL, device=device,
                             torch_dtype=torch.float16 if device == 0 else torch.float32, **kw)
        self._lock = threading.Lock()
        log.info("Hausa-ASR loaded (%s) in %.1fs", config.ASR_MODEL, time.time() - t0)

    def transcribe(self, data: bytes, suffix=".ogg"):
        audio = decode_audio(data, suffix)
        seconds = len(audio) / 16000.0
        with self._lock:
            # the model handles 30 s windows; chunking covers longer voice notes
            try:
                res = self.pipe({"raw": audio, "sampling_rate": 16000}, chunk_length_s=30, batch_size=4,
                                generate_kwargs={"language": "hausa", "task": "transcribe"})
            except Exception:  # some fine-tuned checkpoints reject the language hint
                res = self.pipe({"raw": audio, "sampling_rate": 16000}, chunk_length_s=30, batch_size=4)
        return res["text"].strip(), seconds
