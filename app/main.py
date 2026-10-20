import json, logging, re, sys, uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from app import jobs
from app.config import settings
from app.errors import ApiError, api_error_handler
from app.pipeline.render import SIZES


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

app = FastAPI(title="IncuBrix B-roll Engine", version="0.2.0")
app.add_exception_handler(ApiError, api_error_handler)


async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": {
        "code": "VALIDATION_ERROR", "message": "Invalid request body", "retryable": False,
        "details": {"errors": json.loads(json.dumps(exc.errors(), default=str))}}})


app.add_exception_handler(RequestValidationError, validation_handler)


@app.middleware("http")
async def correlation(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    resp = await call_next(request)
    resp.headers["X-Correlation-Id"] = cid
    log.info(f"{request.method} {request.url.path} {resp.status_code}",
             extra={"correlation_id": cid})
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        jobs._exec("SELECT 1")
    except Exception as e:
        raise ApiError("NOT_READY", str(e), status=503, retryable=True)
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
        if ext not in (".mp3", ".wav", ".m4a"):
            raise ApiError("UNSUPPORTED_FILE_TYPE", "Audio must be .mp3, .wav or .m4a",
                           details={"got": ext or "none"})
    for r in req.aspect_ratios:
        if r not in SIZES:
            raise ApiError("UNSUPPORTED_ASPECT_RATIO", f"{r} is not supported",
                           details={"allowed": list(SIZES)})
    body = {"audio_url": req.audio_url, "script": script.strip() if script else None,
            "voice": req.voice, "aspect_ratios": req.aspect_ratios, "style": req.style,
            "avoid": req.avoid, "captions": req.captions.model_dump(),
            "callback_url": req.callback_url}
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
    return FileResponse(path)