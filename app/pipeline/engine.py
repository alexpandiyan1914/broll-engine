import json, time
from importlib import metadata
from pathlib import Path
from app.config import settings
from app.adapters.registry import get_footage_sources
from app.pipeline import queries, safety
from app.pipeline.queries import make_query, heuristic_query
from app.pipeline.tts import synthesize
from app.pipeline.stt import transcribe
from app.pipeline.scenes import words_to_scenes
from app.pipeline.captions import build_srt, burn_captions
from app.pipeline.render import SIZES, audio_duration, download, normalise_clip, assemble
from app.pipeline.fallback import make_fallback


class PipelineError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def _ver(pkg):
    try:
        return metadata.version(pkg)
    except Exception:
        return "unknown"


def candidate_stream(sources, query_list, orient, dur, used, blocked, warnings, idx):
    """Yield (clip, query, orientation, score) best-first; skips dead sources."""
    seen, dead = set(), set()
    for q in query_list:
        qwords = set(q.lower().split())
        for o in dict.fromkeys([orient, "landscape"]):
            for src in sources:
                if src.name in dead:
                    continue
                try:
                    cands = src.search(q, o, limit=30)
                except Exception as e:
                    dead.add(src.name)
                    warnings.append(f"scene {idx}: source '{src.name}' failed ({str(e)[:100]})")
                    continue
                ok = [c for c in cands if c.clip_id not in used and c.clip_id not in seen
                      and not (safety.tag_set(c.tags) & blocked)]
                ok.sort(key=lambda c: (c.duration < dur, -len(qwords & safety.tag_set(c.tags))))
                for c in ok:
                    seen.add(c.clip_id)
                    yield c, q, o, len(qwords & safety.tag_set(c.tags))


def run_job(script=None, audio_path=None, ratios=("16:9",), style="bright, modern",
            burn_in=True, progress=lambda pct, msg: None, job_id=None, avoid=()):
    t0 = time.time()
    root = Path(settings.data_dir) / (f"jobs/{job_id}" if job_id else f"run_{int(t0)}")
    root.mkdir(parents=True, exist_ok=True)
    warnings, timings = [], {}

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

    try:
        total = audio_duration(narration)
    except Exception:
        raise PipelineError("AUDIO_UNREADABLE", "The audio could not be read (corrupt or unsupported)") from None
    if total > settings.max_audio_seconds:
        raise PipelineError("AUDIO_TOO_LONG",
                            f"Audio is {total:.0f}s; the limit is {settings.max_audio_seconds}s")

    progress(15, "Transcribing with word timestamps")
    t1 = time.time()
    try:
        words, lang = transcribe(narration)
    except Exception:
        raise PipelineError("AUDIO_UNREADABLE", "Speech recognition failed on this audio") from None
    timings["transcribe_s"] = round(time.time() - t1, 1)
    if not words:
        raise PipelineError("NO_SPEECH_DETECTED", "No speech found (silent or music-only audio)")

    scenes = words_to_scenes(words, total, settings.min_scene_seconds)
    (root / "captions.srt").write_text(build_srt(words), encoding="utf-8")
    context = " ".join(w["word"] for w in words)[:200]
    llm_warned = False
    for i, s in enumerate(scenes):
        s["names"] = safety.named_entities(s["text"])
        s["sensitive"] = safety.is_sensitive(s["text"])
        if s["sensitive"]:
            s["query"], s["query_method"] = safety.calm_query(i), "safety-rule"
            warnings.append(f"scene {i}: sensitive topic, used neutral footage without people")
        else:
            s["query"], s["query_method"] = make_query(s["text"], context, style, avoid, s["names"])
            if s["names"]:
                warnings.append(f"scene {i}: named person/brand ({', '.join(s['names'])}) "
                                "not searched; generic footage used")
            if s["query_method"] == "heuristic" and not llm_warned:
                warnings.append("keyword fallback queries in use: " + (queries.last_error or "LLM unavailable"))
                llm_warned = True
        s["blocked"] = safety.blocked_tags(avoid, s["sensitive"])
    progress(25, f"{len(scenes)} scenes planned")

    sources = get_footage_sources()
    files, all_entries, done = {}, [], 0
    total_steps = len(ratios) * len(scenes)
    t2 = time.time()

    for r in ratios:
        tag = r.replace(":", "x")
        orient = "portrait" if r == "9:16" else "landscape"
        used, parts, timeline = set(), [], []
        for i, s in enumerate(scenes):
            dur = s["end"] - s["start"]
            part = root / f"scene_{tag}_{i:02d}.mp4"
            qlist = list(dict.fromkeys([s["query"], heuristic_query(s["text"], s["names"]),
                                        "abstract background"]))
            entry, tries = None, 0
            for c, q, o, score in candidate_stream(sources, qlist, orient, dur, used,
                                                   s["blocked"], warnings, i):
                raw = root / f"raw_{c.clip_id}.mp4"
                try:
                    download(c.download_url, raw)
                    normalise_clip(raw, dur, r, part)
                except Exception as e:
                    raw.unlink(missing_ok=True)
                    warnings.append(f"scene {i}: clip {c.clip_id} unusable ({type(e).__name__}), trying next")
                    tries += 1
                    if tries >= 4:
                        break
                    continue
                used.add(c.clip_id)
                if o != orient:
                    warnings.append(f"scene {i}: no {orient} clips, centre-cropped a {o} clip")
                entry = {"clip_id": c.clip_id, "source": c.source, "url": c.url,
                         "licence": c.licence, "author": c.author,
                         "ai_generated": c.ai_generated, "query": q,
                         "tag_overlap_score": score,
                         "reason": f"best tag overlap ({score}) among unused '{o}' results for '{q}'"}
                break
            if entry is None:
                if not settings.fallback_enabled:
                    raise PipelineError("NO_FOOTAGE", f"No footage found for scene {i}")
                make_fallback(part, dur, r, i)
                warnings.append(f"scene {i}: no usable stock footage, used generated background")
                entry = {"clip_id": f"fallback-{tag}-{i}", "source": "generated-fallback",
                         "url": None, "author": "IncuBrix B-roll Engine",
                         "licence": "Not applicable: procedurally generated by FFmpeg, no third-party content",
                         "ai_generated": False, "query": s["query"], "tag_overlap_score": 0,
                         "reason": "no usable stock clip after retries; neutral generated gradient"}
            parts.append(part)
            timeline.append({"scene": i, "text": s["text"], "start": s["start"], "end": s["end"],
                             "query_method": s["query_method"], "named_entities": s["names"],
                             "sensitive": s["sensitive"], **entry})
            done += 1
            progress(25 + int(65 * done / total_steps), f"{r} scene {i + 1}/{len(scenes)}")

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
        all_entries += timeline
    timings["footage_and_render_s"] = round(time.time() - t2, 1)

    manifest = {
        "warnings": warnings, "language": lang, "audio_seconds": round(total, 2),
        "seconds_total": round(time.time() - t0, 1), "timings": timings,
        "settings": {"ratios": list(ratios), "style": style, "avoid": list(avoid),
                     "burn_in": burn_in, "min_scene_seconds": settings.min_scene_seconds},
        "providers": {"footage": settings.footage_providers, "stt": f"faster-whisper/{settings.whisper_model}",
                      "tts": settings.piper_model,
                      "llm": settings.llm_model if settings.gemini_api_key else "none (keyword fallback)"},
        "versions": {"faster_whisper": _ver("faster-whisper"), "piper_tts": _ver("piper-tts"),
                     "httpx": _ver("httpx"), "app": "0.3.0"},
        "seed": None, "seed_note": "no random sampling; output depends only on inputs and provider results",
        "cost_estimate_usd": 0.0,
        "cost_note": "free-tier APIs and local models only; compute cost not included",
        "rights": {"licences_used": sorted({e["licence"] for e in all_entries}),
                   "ai_generated_clips": sum(1 for e in all_entries if e["ai_generated"]),
                   "generated_fallback_clips": sum(1 for e in all_entries if e["source"] == "generated-fallback"),
                   "all_commercial_use": True}}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    progress(100, "Done")
    return {"folder": str(root), "files": files, "warnings": warnings}