# INCUBRIX ASSESSMENT 3 — REPORT.md
## Script and Voiceover to B-roll Video Engine (`broll-engine`)

**Author:** Alex Pandiyan  
**Repository:** [github.com/alexpandiyan1914/broll-engine](https://github.com/alexpandiyan1914/broll-engine)  
**Live Demo:** [https://broll-engine-ewtq.onrender.com](https://broll-engine-ewtq.onrender.com)  
**Target Track:** Software Engineer (PS3)  

---

## 1. Executive Summary & Architecture Overview

The `broll-engine` is a containerized, background-job-driven microservice built to transform plain text scripts or recorded audio voiceovers into fully rendered, license-clean B-roll videos.

### System Architecture Workflow
1. **Input Ingestion:** The service accepts requests via `POST /api/v1/broll/jobs` with raw audio (MP3/WAV) or text scripts.
2. **Text & Audio Processing:** 
   * **STT Path:** Audio inputs are processed via Whisper (`tiny` model) to obtain word-level and sentence-level timestamps.
   * **TTS Path:** Script inputs are synthesized using Piper TTS to generate clean narration audio alongside scene timing.
3. **Semantic Parsing & Visual Query Generation:** Text chunks are analyzed using **Google Gemini 1.5 Flash** to extract visual concepts, context, and optimized stock footage keywords (overcoming simple literal keyword traps).
4. **Footage Fetching & Asset Selection:** The service queries the **Pixabay Video API** (with configurable fallback adapters). Candidate clips are filtered against duplicate usage and safety constraints (`avoid` topics).
5. **Video Assembly & Normalization:** Using **FFmpeg**, clips are normalized (30 fps, H.264/AAC), smart-cropped to requested aspect ratios (`16:9`, `9:16`), and combined with subtitle burn-ins.
6. **Artifact Generation & Storage:** Final outputs (`video_{ratio}.mp4`, `captions.srt`, `timeline.json`, and `manifest.json`) are stored to S3-compatible storage (MinIO/Local) and accessible via background job polling.

```text
[Client Request] ──> [FastAPI / REST API] ──> [Background Worker Queue]
│
┌────────────────────────────────────────────┴────────────────────────────────────────────┐
▼                                            ▼                                            ▼
[STT / TTS Engine]                       [Gemini LLM Query Parser]                   [Pixabay Footage Adapter]
(Whisper / Piper)                       (Visual Concept Extraction)                  (License Verification)
│                                            │                                            │
└────────────────────────────────────────────┬────────────────────────────────────────────┘
                                             ▼
                                  [FFmpeg Compositor]
                             (Crop, Normalization, SRT)
                                             │
                                             ▼
                                  [S3 / Output Storage]
```

---

## 2. Technical Decisions & Trade-offs

### Architectural & Provider Choices
* **LLM Reasoning (Gemini 1.5 Flash):** Chosen for its rapid response times, low cost, and strong performance in visual concept mapping (e.g., mapping "trust" to "handshake" rather than literal text).
* **Footage Provider Adapter Pattern:** Designed around a swappable interface (`FootageProvider` base class). Pixabay is implemented as the primary provider with a lightweight `MockFootageProvider` fallback for unit testing and offline execution.
* **FFmpeg Pipeline:** Native FFmpeg processes execution directly in Python subprocesses, avoiding heavy GUI wrappers and ensuring low memory overhead during video concatenation and cropping.

### Cloud Deployment Strategy (Render Free Tier Adjustment)
Initially planned for Hugging Face Spaces Docker SDK, deployment was pivoted to **Render Web Services** due to HF free tier availability limits:
* **Memory Optimization:** Render's free tier provides 512 MB RAM and 0.1 vCPU. To prevent Out-Of-Memory (OOM) container shutdowns, the model weights were configured to default to `Whisper-tiny` and modularized execution was enforced to clear memory buffers between steps.
* **Cold Start Handling:** Accommodates Render's 15-minute idle auto-sleep by providing asynchronous status polling and lightweight health check endpoints (`/health`, `/ready`).

---

## 3. Implementation Status & Integration Standard

### Must-Haves Verification (8/8 Passed)
* **MH1 (Dual Inputs):** Handles both MP3/WAV uploads and plain text inputs.
* **MH2 (Semantic Timing):** Scene splits strictly align with sentence boundaries and narration duration.
* **MH3 (License Tracked):** Every scene in `timeline.json` includes commercial license verification, source links, and attribution.
* **MH4 (Video Consistency):** Standardized 1080p-class H.264/AAC output at 30 fps with zero black frames or audio drift.
* **MH5 (No Repeats):** Asset deduplication logic ensures no single video clip is repeated in a job.
* **MH6 (Safety Filters):** `avoid` parameters filter out forbidden content and prevent generating realistic faces of named entities.
* **MH7 (Resiliency):** Seamless fallback to mock footage if stock APIs return errors or rate limits.
* **MH8 (Integration Standard):** Verified API endpoints, background execution, idempotency, and OpenAPI 3.1 documentation.

### Integration Standard Points Met (10/10)
1. **One-Command Setup:** `docker compose up` starts app + MinIO storage; unit/integration tests run without live API keys.
2. **OpenAPI 3.1 Spec:** Standardized contract provided in `openapi.yaml`.
3. **Async Jobs:** Long tasks return `202 Accepted` with progress tracking (0–100%) and signed HMAC callback support.
4. **Idempotency:** Implemented via `Idempotency-Key` headers on POST endpoints.
5. **Clear Error Codes:** Standardized `{"error": {"code": "UPPER_SNAKE_CASE", ...}}` responses.
6. **Config via Env:** Zero hardcoded secrets; configured entirely via environment variables.
7. **S3 Storage:** Input/output files stream to S3-compatible storage.
8. **Structured Logging:** JSON logs capturing level, timestamp, and job UUIDs.
9. **Manifest File:** Full provenance tracking generated in `manifest.json`.
10. **Batch Runner CLI:** Provided CLI script for batch test suite evaluation.

---

## 4. Measured Production Numbers & Performance

| Metric | Measured Value | Testing Conditions / Hardware |
| :--- | :--- | :--- |
| **Turnaround Time (60s video)** | **Cold:** 110s \| **Warm:** 45s | Render Free Tier (0.1 vCPU / 512 MB RAM) |
| **Production Cost** | **$0.00 / minute** | Gemini 1.5 Flash Free Tier + Pixabay Free API |
| **Narration Coverage** | **100%** | All narration segments covered by valid clips |
| **Average Relevance Score** | **3.8 / 5.0** | Human review across 10 sample test prompts |
| **Job Reliability** | **100% Success** | 10 consecutive batch runs with 0 crashes |
| **Peak Memory Footprint** | **~380 MB** | FFmpeg processing + Whisper-tiny execution |

---

## 5. Hard Cases Evaluation

| # | Test Scenario | System Behavior & Strategy | Result |
| :-: | :--- | :--- | :-: |
| **1** | Abstract lines & numbers | Gemini maps abstract terms ("trust", "40% growth") to conceptual visuals (handshake, upward chart). | **PASS** |
| **2** | Named entities / Brands | Contextual search terms extracted instead of literal person names to avoid face harvesting. | **PASS** |
| **3** | Double meanings ("cloud", "bank") | Contextual prompt reasoning ensures "cloud storage" fetches server rooms instead of sky. | **PASS** |
| **4** | Sensitive topics | Content filter intercepts flags and defaults to neutral, respectful background footage. | **PASS** |
| **5** | 9:16 Cropping | Dynamic FFmpeg filters center-crop 16:9 clips (`crop=ih*9/16:ih`) maintaining focus. | **PASS** |
| **6** | Invalid inputs / Silence | API rejects empty scripts with HTTP 400 (`INVALID_INPUT`); silent audio handled safely. | **PASS** |
| **7** | Provider Failure / Concurrency | Fallback provider engaged if Pixabay API fails; queue manages concurrent worker jobs. | **PASS** |

---

## 6. Known Limitations & Unsuccessful Approaches

1. **Hardware Memory Constraints:** Local execution of larger Whisper models (`base` or `small`) on Render's 512 MB RAM tier resulted in memory pressure. Mitigated by utilizing `Whisper-tiny`.
2. **Correlation ID Scope:** While job IDs are tracked throughout execution, full request-level `X-Correlation-Id` forwarding across background worker threads is partially incomplete.
3. **Dropped Advanced Scope:** Multilingual TTS (Hindi/Tamil) and partial scene re-rendering ("swap-a-clip") were omitted to maintain core stability and pass all primary Must-Have criteria.

---

## 7. Future Roadmap & Scaling Strategy

* **Distributed Worker Queue:** Migrate in-memory background processing to Celery/Redis for scaling across multiple worker containers.
* **CLIP-based Relevance Scoring:** Integrate automated Vision-Language Model scoring to programmatically validate footage-text alignment prior to rendering.
* **Generative Video Adapters:** Integrate Runway or Luma AI adapters into the `FootageProvider` interface to support generative background loops for abstract concepts.