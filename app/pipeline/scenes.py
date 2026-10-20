def _dur(g):
    return g[-1]["end"] - g[0]["start"]


def words_to_scenes(words, total, min_len=2.5, max_words=30):
    """Group words into sentence-based scenes that cover 0..total with no gaps."""
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if w["word"][-1] in ".!?" or len(cur) >= max_words:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    merged = []
    for g in groups:
        if merged and _dur(merged[-1]) < min_len:
            merged[-1].extend(g)
        else:
            merged.append(g)
    if len(merged) > 1 and _dur(merged[-1]) < min_len:
        merged[-2].extend(merged.pop())

    scenes = []
    for i, g in enumerate(merged):
        start = 0.0 if i == 0 else g[0]["start"]
        end = merged[i + 1][0]["start"] if i + 1 < len(merged) else total
        scenes.append({"text": " ".join(w["word"] for w in g),
                       "start": round(start, 3), "end": round(end, 3)})
    return scenes