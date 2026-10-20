import subprocess
from pathlib import Path
from app.pipeline.render import SIZES

PALETTE = [("0x1d3557", "0x457b9d"), ("0x264653", "0x2a9d8f"),
           ("0x3d405b", "0x81b29a"), ("0x2b2d42", "0x8d99ae")]


def make_fallback(out: Path, dur: float, ratio: str, idx: int):
    """Animated gradient made by FFmpeg itself: no third-party content, never repeats."""
    w, h = SIZES[ratio]
    c0, c1 = PALETTE[idx % len(PALETTE)]
    src = f"gradients=s={w}x{h}:r=30:d={dur:.3f}:speed=0.02:c0={c0}:c1={c1}:nb_colors=2"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src,
                    "-vf", "format=yuv420p", "-an", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "23", str(out)], check=True)