import json, sys
sys.path.insert(0, ".")
import yaml
from app.main import app

spec = json.loads(json.dumps(app.openapi()))
with open("openapi.yaml", "w", encoding="utf-8") as f:
    f.write(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
print("openapi", spec["openapi"], "-", len(spec["paths"]), "paths written to openapi.yaml")