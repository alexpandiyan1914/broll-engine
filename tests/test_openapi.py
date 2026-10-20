import json
from pathlib import Path
import yaml
from app.main import app


def test_openapi_file_matches_running_service():
    on_disk = yaml.safe_load(Path("openapi.yaml").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(app.openapi())), "run: python scripts/export_openapi.py"
    assert on_disk["openapi"].startswith("3.1")