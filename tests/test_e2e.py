import shutil
from pathlib import Path
import pytest
from app.config import settings
from app.pipeline import engine
from app.pipeline.render import audio_duration

pytestmark = pytest.mark.skipif(
    not (Path(settings.piper_model).exists() and shutil.which("ffmpeg")),
    reason="needs the Piper voice and ffmpeg")


def test_end_to_end_no_api_keys(monkeypatch, tmp_path):
    """Real TTS + Whisper + render. Mock footage cannot be downloaded, so every scene
    must finish on the generated fallback and still produce a complete, consistent video."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "footage_providers", "mock")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    res = engine.run_job(script="Save a little money every week. Small habits build real wealth.",
                         ratios=("16:9",), burn_in=False, job_id="a1b2c3d4e5f6")
    video = Path(res["files"]["16:9"])
    assert video.exists() and video.stat().st_size > 10_000
    tl = __import__("json").loads((video.parent / "timeline_16x9.json").read_text())
    assert tl and all(e["licence"] and e["source"] for e in tl)
    ids = [e["clip_id"] for e in tl]
    assert len(ids) == len(set(ids)), "a clip was reused"
    man = __import__("json").loads((video.parent / "manifest.json").read_text())
    assert abs(audio_duration(video) - man["audio_seconds"]) < 1.0
    assert tl[0]["start"] == 0.0 and abs(tl[-1]["end"] - man["audio_seconds"]) < 0.05