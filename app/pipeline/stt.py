import subprocess
from pathlib import Path
import numpy as np
from app.config import settings

_model = None


def _decode(path: Path) -> np.ndarray:
    """Decode any audio file to 16 kHz mono float32 using the system FFmpeg."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                        "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                       capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise ValueError("ffmpeg could not decode this audio: " + p.stderr.decode(errors="ignore")[:200])
    return np.frombuffer(p.stdout, dtype=np.float32)


def transcribe(path: Path, language: str | None = None):
    """Return ([{word, start, end}], detected_language)."""
    global _model
    from faster_whisper import WhisperModel
    if _model is None:
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    audio = _decode(path)
    segments, info = _model.transcribe(audio, word_timestamps=True,
                                       language=language, vad_filter=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            text = w.word.strip()
            if text:
                words.append({"word": text, "start": float(w.start), "end": float(w.end)})
    return words, info.language