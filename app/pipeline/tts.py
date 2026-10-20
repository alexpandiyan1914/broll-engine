import subprocess, sys
from pathlib import Path
from app.config import settings


def synthesize(text: str, out_wav: Path) -> Path:
    model = Path(settings.piper_model)
    if not model.exists():
        raise FileNotFoundError(f"Piper voice not found: {model.resolve()}")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "piper", "-m", str(model), "-f", str(out_wav)],
                   input=text.encode("utf-8"), check=True)
    return out_wav