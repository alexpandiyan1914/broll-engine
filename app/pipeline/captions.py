import subprocess
from pathlib import Path


def _ts(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def build_srt(words, max_words=7):
    cues, cur = [], []

    def flush():
        if cur:
            cues.append((cur[0]["start"], cur[-1]["end"], " ".join(w["word"] for w in cur)))
            cur.clear()

    for w in words:
        cur.append(w)
        last = w["word"][-1]
        if last in ".!?" or len(cur) >= max_words or (last == "," and len(cur) >= 4):
            flush()
    flush()
    return "".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n"
                   for i, (a, b, t) in enumerate(cues, 1))


def burn_captions(workdir: Path, video_in: str, srt: str, video_out: str):
    # relative names + cwd avoids Windows drive-letter escaping problems in the filter
    style = "FontName=Arial,FontSize=16,Outline=2,Shadow=0,MarginV=40,Alignment=2"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_in,
                    "-vf", f"subtitles={srt}:force_style='{style}'",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "copy", video_out],
                   cwd=workdir, check=True)