"""Run every input in a folder (or one file) against the API and save all results.
.txt = script text, .json = a full request body (e.g. with audio_url)."""
import argparse, json, sys, time, uuid
from pathlib import Path
import httpx


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", help="folder or single .txt/.json file")
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--out", default="batch_out")
    p.add_argument("--ratios", default="16:9")
    p.add_argument("--token", default="")
    p.add_argument("--timeout", type=int, default=1800)
    a = p.parse_args()

    src = Path(a.inputs)
    items = sorted(src.glob("*")) if src.is_dir() else [src]
    items = [f for f in items if f.suffix.lower() in (".txt", ".json")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    hdr = {"Authorization": f"Bearer {a.token}"} if a.token else {}
    summary = []

    with httpx.Client(base_url=a.api, headers=hdr, timeout=60) as c:
        for f in items:
            name = f.stem
            folder = out / name
            folder.mkdir(parents=True, exist_ok=True)
            body = (json.loads(f.read_text(encoding="utf-8")) if f.suffix == ".json"
                    else {"script": f.read_text(encoding="utf-8")})
            body.setdefault("aspect_ratios", a.ratios.split(","))
            t0 = time.time()
            r = c.post("/api/v1/broll/jobs", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})
            if r.status_code != 202:
                (folder / "error.json").write_text(r.text, encoding="utf-8")
                summary.append({"input": f.name, "status": "rejected", "error": r.json().get("error")})
                print(f"{f.name}: rejected {r.status_code}")
                continue
            jid = r.json()["job_id"]
            job = {}
            while time.time() - t0 < a.timeout:
                job = c.get(f"/api/v1/jobs/{jid}").json()
                if job["status"] in ("succeeded", "failed"):
                    break
                time.sleep(3)
            (folder / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
            if job.get("status") == "succeeded":
                for fname, link in job["result"]["files"].items():
                    d = c.get(link)
                    if d.status_code == 200:
                        (folder / fname).write_bytes(d.content)
            summary.append({"input": f.name, "job_id": jid, "status": job.get("status"),
                            "seconds": round(time.time() - t0, 1),
                            "warnings": (job.get("result") or {}).get("warnings", []),
                            "error": job.get("error")})
            print(f"{f.name}: {job.get('status')} in {summary[-1]['seconds']}s")

    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    ok = sum(1 for s in summary if s["status"] == "succeeded")
    print(f"{ok}/{len(summary)} succeeded -> {out}")
    sys.exit(0 if ok == len(summary) else 1)


if __name__ == "__main__":
    main()