import hashlib, hmac, json, logging, sqlite3, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
import httpx
from app.config import settings
from app.errors import ApiError
from app.pipeline import engine

log = logging.getLogger("broll")
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=max(1, settings.max_concurrent_jobs))
PUBLIC_FILES = ("captions.srt", "timeline.json", "manifest.json")
RETRYABLE = {"NO_FOOTAGE", "AUDIO_DOWNLOAD_FAILED", "INTERNAL_ERROR"}


def _conn():
    p = Path(settings.data_dir)
    p.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p / "jobs.db", check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, idem_key TEXT UNIQUE, body_hash TEXT, request TEXT,
        status TEXT, progress INTEGER, message TEXT, result TEXT, error TEXT, created REAL)""")
    return c


def _exec(sql, args=()):
    c = _conn()
    try:
        rows = c.execute(sql, args).fetchall()
        c.commit()
        return rows
    finally:
        c.close()


def _public(r):
    return {"job_id": r["id"], "status": r["status"], "progress": r["progress"],
            "message": r["message"],
            "result": json.loads(r["result"]) if r["result"] else None,
            "error": json.loads(r["error"]) if r["error"] else None}


def get_job(job_id):
    rows = _exec("SELECT * FROM jobs WHERE id=?", (job_id,))
    return _public(rows[0]) if rows else None


def _update(job_id, **f):
    for k in ("result", "error"):
        if f.get(k) is not None:
            f[k] = json.dumps(f[k])
    sets = ", ".join(f"{k}=?" for k in f)
    _exec(f"UPDATE jobs SET {sets} WHERE id=?", (*f.values(), job_id))


def create_job(req: dict, key):
    body_hash = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
    with _lock:
        if key:
            rows = _exec("SELECT * FROM jobs WHERE idem_key=?", (key,))
            if rows:
                if rows[0]["body_hash"] != body_hash:
                    raise ApiError("IDEMPOTENCY_KEY_REUSED",
                                   "This Idempotency-Key was used with a different request",
                                   status=409)
                return _public(rows[0]), False
        job_id = uuid.uuid4().hex[:12]
        _exec("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
              (job_id, key, body_hash, json.dumps(req), "queued", 0, "Queued",
               None, None, time.time()))
    _pool.submit(_run, job_id)
    return get_job(job_id), True


def _fetch_audio(url, root: Path):
    ext = Path(urlparse(url).path).suffix.lower()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"input{ext}"
    limit = settings.max_audio_mb * 1024 * 1024
    size = 0
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise engine.PipelineError("AUDIO_TOO_LARGE",
                                                   f"Audio is larger than {settings.max_audio_mb} MB")
                    f.write(chunk)
    except httpx.HTTPError as e:
        raise engine.PipelineError("AUDIO_DOWNLOAD_FAILED", str(e))
    return dest


def _write_timeline(root: Path, ratios):
    combined = {}
    for r in ratios:
        p = root / f"timeline_{r.replace(':', 'x')}.json"
        if p.exists():
            combined[r] = json.loads(p.read_text(encoding="utf-8"))
    (root / "timeline.json").write_text(json.dumps(combined, indent=2), encoding="utf-8")


def _run(job_id):
    req = json.loads(_exec("SELECT * FROM jobs WHERE id=?", (job_id,))[0]["request"])
    root = Path(settings.data_dir) / "jobs" / job_id
    extra = {"job_id": job_id}
    try:
        _update(job_id, status="running", progress=1, message="Starting")
        log.info("job started", extra=extra)
        audio = _fetch_audio(req["audio_url"], root) if req.get("audio_url") else None
        res = engine.run_job(
            script=req.get("script"), audio_path=audio, ratios=req["aspect_ratios"],
            style=req["style"], burn_in=req["captions"]["burn_in"],
            progress=lambda pct, msg: _update(job_id, progress=int(pct), message=msg),
            job_id=job_id)
        _write_timeline(root, req["aspect_ratios"])
        names = [f"video_{r.replace(':', 'x')}.mp4" for r in req["aspect_ratios"]]
        names += list(PUBLIC_FILES)
        files = {n: f"/api/v1/jobs/{job_id}/files/{n}" for n in names if (root / n).exists()}
        _update(job_id, status="succeeded", progress=100, message="Done",
                result={"files": files, "warnings": res["warnings"]})
        log.info("job succeeded", extra=extra)
    except engine.PipelineError as e:
        _update(job_id, status="failed", message=e.message,
                error={"code": e.code, "message": e.message,
                       "retryable": e.code in RETRYABLE, "details": {}})
        log.warning(f"job failed: {e.code}", extra=extra)
    except Exception as e:
        log.exception("job crashed", extra=extra)
        _update(job_id, status="failed", message="Internal error",
                error={"code": "INTERNAL_ERROR", "message": str(e)[:300],
                       "retryable": True, "details": {}})
    if req.get("callback_url"):
        _callback(job_id, req["callback_url"])


def _callback(job_id, url):
    body = json.dumps(get_job(job_id)).encode()
    sig = hmac.new(settings.callback_secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        httpx.post(url, content=body, timeout=10,
                   headers={"Content-Type": "application/json",
                            "X-IncuBrix-Signature": f"sha256={sig}"})
    except Exception as e:
        log.warning(f"callback failed: {e}", extra={"job_id": job_id})