import json, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from app.config import settings
from app.adapters.registry import get_footage_sources
from app.pipeline.segment import split_sentences
from app.pipeline.queries import make_query
from app.pipeline.tts import synthesize
from app.pipeline.render import audio_duration, download, normalise_clip, assemble

def run(script: str, ratio="16:9"):
    t0 = time.time()
    root = Path(settings.data_dir) / f"run_{int(t0)}"
    root.mkdir(parents=True, exist_ok=True)
    warnings = []

    sentences = split_sentences(script)
    if not sentences:
        raise SystemExit("EMPTY_SCRIPT")
    narration = synthesize(" ".join(sentences), root / "narration.wav")
    total = audio_duration(narration)

    # time each scene by its share of the words (Day 3: replace with real alignment)
    words = [max(len(s.split()), 1) for s in sentences]
    durs = [total * w / sum(words) for w in words]

    sources, used, parts, timeline, cursor = get_footage_sources(), set(), [], [], 0.0
    orient = "portrait" if ratio == "9:16" else "landscape"

    for i, (sent, dur) in enumerate(zip(sentences, durs)):
        query, how = make_query(sent, script[:200])
        chosen = None
        for src in sources:
            try:
                cands = [c for c in src.search(query, orient) if c.clip_id not in used]
            except Exception as e:
                warnings.append(f"scene {i}: {src.name} failed: {e}")
                continue
            if cands:
                long_enough = [c for c in cands if c.duration >= dur]
                chosen = (long_enough or cands)[0]
                break
        if not chosen:
            query = "abstract background"
            warnings.append(f"scene {i}: no result, used fallback query")
            for src in sources:
                cands = [c for c in src.search(query, orient) if c.clip_id not in used]
                if cands:
                    chosen = cands[0]; break
        if not chosen:
            raise SystemExit(f"No footage for scene {i}")

        used.add(chosen.clip_id)
        raw = download(chosen.download_url, root / f"raw_{chosen.clip_id}.mp4")
        part = root / f"scene_{i:02d}.mp4"
        normalise_clip(raw, dur, ratio, part)
        parts.append(part)
        timeline.append({"scene": i, "text": sent, "start": round(cursor, 2),
            "end": round(cursor + dur, 2), "query": query, "query_method": how,
            "clip_id": chosen.clip_id, "source": chosen.source, "url": chosen.url,
            "licence": chosen.licence, "author": chosen.author,
            "ai_generated": chosen.ai_generated,
            "reason": f"first unused result for query '{query}'"})
        cursor += dur
        print(f"scene {i}: '{query}' -> {chosen.clip_id}")

    out = root / f"video_{ratio.replace(':', 'x')}.mp4"
    assemble(parts, narration, out)
    (root / "timeline.json").write_text(json.dumps(timeline, indent=2))
    (root / "manifest.json").write_text(json.dumps({
        "warnings": warnings, "seconds": round(time.time() - t0, 1),
        "providers": settings.footage_providers}, indent=2))
    print("DONE:", out)

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "16:9")
