---
title: B-roll Engine
sdk: docker
app_port: 7860
---

# IncuBrix B-roll Engine

Turns a script or a voiceover into a finished video: narration, stock footage matched by meaning,
captions, and a per-clip record of source, licence and author.

## Architecture

POST /api/v1/broll/jobs (json) | /jobs/upload (audio) -> 202 + job_id (SQLite job table, 1 worker thread)
script -> Piper TTS --
audio ---------------+--> Whisper word timestamps -> scenes on sentence boundaries (min length setting)
scene text -> LLM (or keyword fallback) + safety rules -> search query
Pixabay search -> filter (avoid / sensitive) -> tag-overlap ranking -> download -> FFmpeg normalise
(a failing source or bad clip -> next candidate -> generated gradient fallback, flagged in timeline)
concat + narration + burned captions -> video_{ratio}.mp4, captions.srt, timeline.json, manifest.json
outputs -> local disk or S3/MinIO (presigned download links)


## Quick start (docker)

cp .env.example .env # add PIXABAY_API_KEY and optionally GEMINI_API_KEY
docker compose up --build # UI + API at http://localhost:8000, MinIO console at :9001
docker compose run --rm api pytest -q
python scripts/batch.py batch_in --api http://localhost:8000 --out batch_out


## Local development

python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m piper.download_voices en_US-lessac-medium --download-dir models
uvicorn app.main:app --port 8000
pytest -q


## API

Full contract: `openapi.yaml` (regenerate with `python scripts/export_openapi.py`; a test checks it matches the service).
All routes are under `/api/v1/`. Send `Authorization: Bearer <token>` when `API_TOKEN` is set.

- `POST /api/v1/broll/jobs` (JSON: `script`, `scenes`, or `audio_url`, `aspect_ratios`, `style`, `avoid`, `captions`, `callback_url`) returns 202 and `job_id`
- `POST /api/v1/broll/jobs/upload` (multipart `audio`, plus form fields) returns 202 and `job_id`
- `GET /api/v1/jobs/{job_id}` returns status (queued, running, succeeded, failed), progress and result links
- `GET /api/v1/jobs/{job_id}/files/{name}` downloads an output
- `GET /health`, `GET /ready`
- Every POST accepts an `Idempotency-Key` header. Callbacks are signed with HMAC-SHA256 in `X-IncuBrix-Signature`.

## Settings

All settings are environment variables; see `.env.example` for the full list and defaults.

## Error format and codes

```json
{"error": {"code": "EMPTY_INPUT", "message": "...", "retryable": false, "details": {}}}
```

| Code | HTTP | Meaning |
|---|---|---|
| VALIDATION_ERROR | 400 | Request body does not match the schema |
| EMPTY_INPUT | 400 | No script, scenes, audio_url, or the uploaded file is empty |
| AMBIGUOUS_INPUT | 400 | Both audio and script were sent |
| UNSUPPORTED_FILE_TYPE | 400 | Audio is not mp3, wav or m4a |
| UNSUPPORTED_ASPECT_RATIO | 400 | Ratio not in 16:9, 9:16, 1:1 |
| UNAUTHORIZED | 401 | Missing or invalid access token |
| JOB_NOT_FOUND / FILE_NOT_FOUND | 404 | Unknown job or file |
| IDEMPOTENCY_KEY_REUSED | 409 | Same key used with a different request |
| FILE_TOO_LARGE | 413 | Upload exceeds MAX_AUDIO_MB |
| RATE_LIMITED | 429 | Too many requests (retryable) |
| NOT_READY | 503 | Database or storage unavailable (retryable) |

Codes that appear in a failed job's `error` field:
AUDIO_NOT_FOUND, AUDIO_UNREADABLE, AUDIO_TOO_LONG, AUDIO_TOO_LARGE, AUDIO_DOWNLOAD_FAILED (retryable),
NO_SPEECH_DETECTED, NO_FOOTAGE (only when the generated fallback is disabled), INTERNAL_ERROR (retryable).

## Known limitations

- Relevance is estimated from tag overlap (Pixabay tags), not a vision model.
- One stock source (Pixabay) plus a generated fallback; no AI video generation.
- Narration from text is English only (Piper en_US voice).
- `visual_hint` in scene lists is accepted but not used yet; clips cannot be swapped after rendering.
- Free hosting has ephemeral disk and sleeps when idle, so jobs do not survive a restart.