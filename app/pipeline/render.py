import subprocess, json
from pathlib import Path
import httpx

SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}

def audio_duration(path: Path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])

def download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest

def normalise_clip(src: Path, dur: float, ratio: str, out: Path):
    w, h = SIZES[ratio]
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
          f"crop={w}:{h},fps=30,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1",
        "-i", str(src), "-t", f"{dur:.3f}", "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(out)], check=True)

def assemble(parts: list[Path], narration: Path, out: Path):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(lst), "-i", str(narration), "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)], check=True)