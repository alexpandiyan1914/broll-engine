import json, time
from pathlib import Path
from app.config import settings
from app.adapters.registry import get_footage_sources
from app.pipeline.queries import make_query, heuristic_query
from app.pipeline.tts import synthesize
from app.pipeline.stt import transcribe
from app.pipeline.scenes import words_to_scenes
from app.pipeline.captions import build_srt, burn_captions
from app.pipeline.render import SIZES, audio_duration, download, normalise_clip, assemble


class PipelineError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def _score(c, qwords):
    tags = set(c.tags.lower().replace(",", " ").split())
    return len(qwords & tags)


def pick_clip(sources, queries, orient, dur, used, warnings, idx):
    for qi, q in enumerate(queries):
        qwords = set(q.lower().split())
        for o in dict.fromkeys([orient, "landscape"]):
            for src in sources:
                try:
                    cands = [c for c in src.search(q, o, limit=30) if c.clip_id not in used]
                except Exception as e:
                    warnings.append(f"scene {idx}: {src.name} failed: {e}")
                    continue
                if cands:
                    pool = [c for c in cands if c.duration >= dur] or cands
                    best = max(pool, key=lambda c: _score(c, qwords))
                    if qi > 0:
                        warnings.append(f"scene {idx}: used fallback query '{q}'")
                    if o != orient:
                        warnings.append(f"scene {idx}: no {orient} clips, centre-cropped a {o} clip")
                    return best, q, o, _score(best, qwords)
    return None, None, None, 0


def run_job(script=None, audio_path=None, ratios=("16:9",), style="bright, modern",
            burn_in=True, progress=lambda pct, msg: None, job_id=None):
    t0 = time.time()
    root = Path(settings.data_dir) / (f"jobs/{job_id}" if job_id else f"run_{int(t0)}")
    root.mkdir(parents=True, exist_ok=True)
    warnings = []

    for r in ratios:
        if r not in SIZES:
            raise PipelineError("UNSUPPORTED_ASPECT_RATIO", f"{r} not in {list(SIZES)}")

    if audio_path:
        narration = Path(audio_path)
        if not narration.exists():
            raise PipelineError("AUDIO_NOT_FOUND", f"No such file: {audio_path}")
    elif script and script.strip():
        progress(5, "Synthesising narration")
        narration = synthesize(script.strip(), root / "narration.wav")
    else:
        raise PipelineError("EMPTY_INPUT", "Provide a script or an audio file")

    progress(15, "Transcribing with word timestamps")
    words, lang = transcribe(narration)
    if not words:
        raise PipelineError("NO_SPEECH_DETECTED", "No speech found in the audio")
    total = audio_duration(narration)

    scenes = words_to_scenes(words, total, settings.min_scene_seconds)
    (root / "captions.srt").write_text(build_srt(words), encoding="utf-8")
    context = " ".join(w["word"] for w in words)[:200]
    for i, s in enumerate(scenes):
        s["query"], s["query_method"] = make_query(s["text"], context, style)
        if s["query_method"] == "heuristic":
            warnings.append(f"scene {i}: keyword fallback query (LLM unavailable or failed)")
    progress(25, f"{len(scenes)} scenes planned")

    sources = get_footage_sources()
    files, steps_done = {}, 0
    total_steps = len(ratios) * len(scenes)

    for r in ratios:
        tag = r.replace(":", "x")
        orient = "portrait" if r == "9:16" else "landscape"
        used, parts, timeline = set(), [], []
        for i, s in enumerate(scenes):
            dur = s["end"] - s["start"]
            queries = list(dict.fromkeys([s["query"], heuristic_query(s["text"]), "abstract background"]))
            chosen, q, o, score = pick_clip(sources, queries, orient, dur, used, warnings, i)
            if not chosen:
                raise PipelineError("NO_FOOTAGE", f"No footage found for scene {i}: {s['text']}")
            used.add(chosen.clip_id)
            raw = download(chosen.download_url, root / f"raw_{chosen.clip_id}.mp4")
            part = root / f"scene_{tag}_{i:02d}.mp4"
            normalise_clip(raw, dur, r, part)
            parts.append(part)
            timeline.append({
                "scene": i, "text": s["text"], "start": s["start"], "end": s["end"],
                "query": q, "query_method": s["query_method"],
                "clip_id": chosen.clip_id, "source": chosen.source, "url": chosen.url,
                "licence": chosen.licence, "author": chosen.author,
                "ai_generated": chosen.ai_generated,
                "tag_overlap_score": score,
                "reason": f"best tag overlap ({score}) among unused '{o}' results for '{q}'"})
            steps_done += 1
            progress(25 + int(65 * steps_done / total_steps), f"{r} scene {i + 1}/{len(scenes)}")

        raw_out = root / f"video_{tag}_raw.mp4"
        assemble(parts, narration, raw_out)
        final = root / f"video_{tag}.mp4"
        if burn_in:
            progress(92, f"Burning captions ({r})")
            burn_captions(root, raw_out.name, "captions.srt", final.name)
        else:
            raw_out.replace(final)
        (root / f"timeline_{tag}.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        files[r] = str(final)

    manifest = {"warnings": warnings, "seconds": round(time.time() - t0, 1),
                "language": lang, "audio_seconds": round(total, 2),
                "providers": settings.footage_providers, "whisper_model": settings.whisper_model,
                "llm_model": settings.llm_model, "tts_model": settings.piper_model,
                "min_scene_seconds": settings.min_scene_seconds}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    progress(100, "Done")
    return {"folder": str(root), "files": files, "warnings": warnings}