import hashlib, hmac, json, logging, re, sys, time, uuid
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from app import jobs, storage
from app.config import settings
from app.errors import ApiError, api_error_handler
from app.pipeline.render import SIZES

AUDIO_EXT = (".mp3", ".wav", ".m4a")


class JsonFormatter(logging.Formatter):
    def format(self, r):
        return json.dumps({"timestamp": self.formatTime(r), "level": r.levelname,
                           "message": r.getMessage(),
                           "job_id": getattr(r, "job_id", None),
                           "correlation_id": getattr(r, "correlation_id", None)})


h = logging.StreamHandler(sys.stdout)
h.setFormatter(JsonFormatter())
logging.basicConfig(level=settings.log_level, handlers=[h], force=True)
log = logging.getLogger("broll")

app = FastAPI(title="IncuBrix B-roll Engine", version="0.4.0")
app.add_exception_handler(ApiError, api_error_handler)


async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": {
        "code": "VALIDATION_ERROR", "message": "Invalid request body", "retryable": False,
        "details": {"errors": json.loads(json.dumps(exc.errors(), default=str))}}})


app.add_exception_handler(RequestValidationError, validation_handler)


def _err(status, code, message, retryable=False):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "retryable": retryable, "details": {}}})


_hits = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    path, resp = request.url.path, None
    if path.startswith("/api/v1/"):
        if settings.api_token:
            auth = request.headers.get("authorization", "")
            tok = auth[7:].strip() if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
            if not hmac.compare_digest(tok.encode(), settings.api_token.encode()):
                resp = _err(401, "UNAUTHORIZED", "Missing or invalid access token")
        if resp is None and request.method == "POST":
            fwd = request.headers.get("x-forwarded-for")
            ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
            now, q = time.time(), _hits[ip]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= settings.rate_limit_per_min:
                resp = _err(429, "RATE_LIMITED", "Too many requests, try again shortly", True)
            else:
                q.append(now)
    if resp is None:
        resp = await call_next(request)
    resp.headers["X-Correlation-Id"] = cid
    log.info(f"{request.method} {path} {resp.status_code}", extra={"correlation_id": cid})
    return resp


class Captions(BaseModel):
    burn_in: bool = True
    srt: bool = True


class JobRequest(BaseModel):
    audio_url: str | None = None
    script: str | None = None
    scenes: list[dict] | None = None
    voice: str = "en-US"
    aspect_ratios: list[str] = ["16:9"]
    style: str = "bright, modern, real-world footage"
    avoid: list[str] = []
    captions: Captions = Captions()
    callback_url: str | None = None


def _check_ratios(ratios):
    if not ratios:
        raise ApiError("UNSUPPORTED_ASPECT_RATIO", "Choose at least one aspect ratio",
                       details={"allowed": list(SIZES)})
    for r in ratios:
        if r not in SIZES:
            raise ApiError("UNSUPPORTED_ASPECT_RATIO", f"{r} is not supported",
                           details={"allowed": list(SIZES)})


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        jobs._exec("SELECT 1")
        storage.check()
    except Exception as e:
        raise ApiError("NOT_READY", str(e)[:200], status=503, retryable=True)
    return {"status": "ready"}


@app.post("/api/v1/broll/jobs", status_code=202)
def create(req: JobRequest, idempotency_key: str | None = Header(default=None)):
    script = req.script
    if req.scenes and not script:
        script = " ".join(str(s.get("text", "")).strip() for s in req.scenes)
    if req.audio_url and script and script.strip():
        raise ApiError("AMBIGUOUS_INPUT", "Send either audio_url or script/scenes, not both")
    if not req.audio_url and not (script and script.strip()):
        raise ApiError("EMPTY_INPUT", "Provide a non-empty script, scenes or audio_url")
    if req.audio_url:
        ext = Path(urlparse(req.audio_url).path).suffix.lower()
        if ext not in AUDIO_EXT:
            raise ApiError("UNSUPPORTED_FILE_TYPE", "Audio must be .mp3, .wav or .m4a",
                           details={"got": ext or "none"})
    _check_ratios(req.aspect_ratios)
    body = {"audio_url": req.audio_url, "script": script.strip() if script else None,
            "voice": req.voice, "aspect_ratios": req.aspect_ratios, "style": req.style,
            "avoid": req.avoid, "captions": req.captions.model_dump(),
            "callback_url": req.callback_url}
    job, _ = jobs.create_job(body, idempotency_key)
    return {"job_id": job["job_id"], "status": job["status"],
            "status_url": f"/api/v1/jobs/{job['job_id']}"}


@app.post("/api/v1/broll/jobs/upload", status_code=202)
async def create_upload(audio: UploadFile = File(...),
                        aspect_ratios: str = Form("16:9"),
                        style: str = Form("bright, modern, real-world footage"),
                        avoid: str = Form(""),
                        burn_in: bool = Form(True),
                        idempotency_key: str | None = Header(default=None)):
    ext = Path(audio.filename or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise ApiError("UNSUPPORTED_FILE_TYPE", "Audio must be .mp3, .wav or .m4a",
                       details={"got": ext or "none"})
    ratios = [r.strip() for r in aspect_ratios.split(",") if r.strip()]
    _check_ratios(ratios)
    up = Path(settings.data_dir) / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    tmp = up / f"{uuid.uuid4().hex}{ext}"
    sha, size, too_big = hashlib.sha256(), 0, False
    limit = settings.max_audio_mb * 1024 * 1024
    with open(tmp, "wb") as f:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                too_big = True
                break
            sha.update(chunk)
            f.write(chunk)
    if too_big:
        tmp.unlink(missing_ok=True)
        raise ApiError("FILE_TOO_LARGE", f"Audio is larger than {settings.max_audio_mb} MB", status=413)
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise ApiError("EMPTY_INPUT", "The uploaded audio file is empty")
    final = up / f"{sha.hexdigest()}{ext}"
    tmp.replace(final)
    body = {"audio_url": None, "audio_path": str(final), "audio_sha256": sha.hexdigest(),
            "script": None, "voice": "en-US", "aspect_ratios": ratios, "style": style,
            "avoid": [a.strip() for a in avoid.split(",") if a.strip()],
            "captions": {"burn_in": burn_in, "srt": True}, "callback_url": None}
    job, _ = jobs.create_job(body, idempotency_key)
    return {"job_id": job["job_id"], "status": job["status"],
            "status_url": f"/api/v1/jobs/{job['job_id']}"}


@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise ApiError("JOB_NOT_FOUND", "No such job", status=404)
    return job


@app.get("/api/v1/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    ok_name = name in jobs.PUBLIC_FILES or re.fullmatch(r"video_(16x9|9x16|1x1)\.mp4", name)
    path = Path(settings.data_dir) / "jobs" / job_id / name
    if not re.fullmatch(r"[0-9a-f]{12}", job_id) or not ok_name or not path.is_file():
        raise ApiError("FILE_NOT_FOUND", "No such file", status=404)
    if storage.enabled():
        return RedirectResponse(storage.download_url(job_id, name), status_code=307)
    return FileResponse(path)