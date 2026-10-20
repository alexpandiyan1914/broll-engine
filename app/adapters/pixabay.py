import hashlib, json, time
from pathlib import Path
import httpx
from app.config import settings
from .base import ClipCandidate

CACHE_TTL = 24 * 3600  # Pixabay terms: cache responses for 24h


class PixabayFootage:
    name = "pixabay"

    def _get(self, params):
        cache_dir = Path(settings.data_dir) / "cache" / "pixabay"
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()
        f = cache_dir / f"{key}.json"
        if f.exists() and time.time() - f.stat().st_mtime < CACHE_TTL:
            return json.loads(f.read_text(encoding="utf-8"))
        r = httpx.get("https://pixabay.com/api/videos/",
                      params={**params, "key": settings.pixabay_api_key}, timeout=20)
        r.raise_for_status()
        data = r.json()
        f.write_text(json.dumps(data), encoding="utf-8")
        return data

    def search(self, query, orientation="landscape", limit=8):
        data = self._get({"q": query[:100], "video_type": "film",
                          "safesearch": "true", "per_page": 60, "order": "popular"})
        out = []
        for v in data.get("hits", []):
            sizes = [s for s in ("large", "medium", "small")
                     if v.get("videos", {}).get(s, {}).get("url")]
            if not sizes:
                continue
            s = v["videos"][sizes[0]]
            w, h = s.get("width") or 0, s.get("height") or 0
            if orientation == "portrait" and h < w:
                continue
            if orientation == "landscape" and w < h:
                continue
            out.append(ClipCandidate(
                clip_id=f"pixabay-{v['id']}", source="pixabay", url=v["pageURL"],
                download_url=s["url"], duration=float(v["duration"]),
                width=w, height=h,
                licence="Pixabay Content License (commercial use allowed, no attribution required)",
                author=v.get("user", "unknown"),
                tags=v.get("tags", ""),
            ))
            if len(out) >= limit:
                break
        return out