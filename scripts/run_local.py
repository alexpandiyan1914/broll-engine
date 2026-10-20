import argparse, json, sys
sys.path.insert(0, ".")
from app.pipeline.engine import run_job, PipelineError

p = argparse.ArgumentParser()
p.add_argument("script", nargs="?")
p.add_argument("--audio")
p.add_argument("--ratios", default="16:9")
p.add_argument("--avoid", default="")
p.add_argument("--no-burn", action="store_true")
a = p.parse_args()

try:
    res = run_job(script=a.script, audio_path=a.audio, ratios=a.ratios.split(","),
                  burn_in=not a.no_burn,
                  avoid=[x.strip() for x in a.avoid.split(",") if x.strip()],
                  progress=lambda pct, msg: print(f"[{pct:3d}%] {msg}"))
except PipelineError as e:
    sys.exit(f"{e.code}: {e.message}")
print(json.dumps(res, indent=2))