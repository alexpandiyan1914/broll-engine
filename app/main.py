import json, logging, sys, uuid
from fastapi import FastAPI, Request
from app.config import settings
from app.errors import ApiError, api_error_handler

class JsonFormatter(logging.Formatter):
    def format(self, r):
        return json.dumps({"timestamp": self.formatTime(r), "level": r.levelname,
            "message": r.getMessage(), "job_id": getattr(r, "job_id", None),
            "correlation_id": getattr(r, "correlation_id", None)})

h = logging.StreamHandler(sys.stdout); h.setFormatter(JsonFormatter())
logging.basicConfig(level=settings.log_level, handlers=[h])
log = logging.getLogger("broll")

app = FastAPI(title="IncuBrix B-roll Engine", version="0.1.0")
app.add_exception_handler(ApiError, api_error_handler)

@app.middleware("http")
async def correlation(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    request.state.cid = cid
    resp = await call_next(request)
    resp.headers["X-Correlation-Id"] = cid
    log.info(f"{request.method} {request.url.path} {resp.status_code}",
             extra={"correlation_id": cid})
    return resp

@app.get("/")
def root():
    return {"message": "IncuBrix B-roll Engine running"}

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/ready")
def ready(): return {"status": "ready"}   # later: check Redis and MinIO