import mimetypes
import threading
from pathlib import Path
from app.config import settings

_ready = False
_lock = threading.Lock()


def enabled() -> bool:
    return settings.storage_backend == "s3"


def _client(endpoint):
    import boto3
    from botocore.client import Config
    return boto3.client("s3", endpoint_url=endpoint,
                        aws_access_key_id=settings.s3_access_key,
                        aws_secret_access_key=settings.s3_secret_key,
                        region_name="us-east-1",
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))


def ensure_bucket():
    global _ready
    with _lock:
        if _ready:
            return
        c = _client(settings.s3_endpoint)
        try:
            c.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            c.create_bucket(Bucket=settings.s3_bucket)
        _ready = True


def check():
    if enabled():
        ensure_bucket()


def publish(job_id: str, path: Path):
    if not enabled():
        return
    ensure_bucket()
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    _client(settings.s3_endpoint).upload_file(
        str(path), settings.s3_bucket, f"jobs/{job_id}/{path.name}",
        ExtraArgs={"ContentType": ctype})


def download_url(job_id: str, name: str, expires: int = 3600) -> str:
    c = _client(settings.s3_public_endpoint or settings.s3_endpoint)
    return c.generate_presigned_url(
        "get_object", ExpiresIn=expires,
        Params={"Bucket": settings.s3_bucket, "Key": f"jobs/{job_id}/{name}"})