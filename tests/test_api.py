import time
from pathlib import Path
from fastapi.testclient import TestClient
from app import jobs
from app.main import app
from app.pipeline import engine


def fake_run_job(script=None, audio_path=None, ratios=("16:9",), style="", burn_in=True,
                 progress=lambda p, m: None, job_id=None):
    root = Path(jobs.settings.data_dir) / "jobs" / job_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "video_16x9.mp4").write_bytes(b"x")
    (root / "manifest.json").write_text("{}")
    progress(50, "half")
    return {"folder": str(root), "files": {}, "warnings": ["w"]}


def test_job_flow_idempotency_and_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(engine, "run_job", fake_run_job)
    c = TestClient(app)
    body = {"script": "Hello world. This is a test."}
    h = {"Idempotency-Key": "k1"}
    r1 = c.post("/api/v1/broll/jobs", json=body, headers=h)
    r2 = c.post("/api/v1/broll/jobs", json=body, headers=h)
    assert r1.status_code == 202 and r1.json()["job_id"] == r2.json()["job_id"]
    jid = r1.json()["job_id"]
    for _ in range(60):
        s = c.get(f"/api/v1/jobs/{jid}").json()
        if s["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.1)
    assert s["status"] == "succeeded" and s["progress"] == 100
    assert "video_16x9.mp4" in s["result"]["files"]
    assert c.get(s["result"]["files"]["video_16x9.mp4"]).status_code == 200

    clash = c.post("/api/v1/broll/jobs", json={"script": "Different."}, headers=h)
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    bad = c.post("/api/v1/broll/jobs", json={"script": "   "})
    e = bad.json()["error"]
    assert bad.status_code == 400 and e["code"] == "EMPTY_INPUT"
    assert set(e) == {"code", "message", "retryable", "details"}

    wrong = c.post("/api/v1/broll/jobs", json={"audio_url": "https://x.test/a.txt"})
    assert wrong.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"