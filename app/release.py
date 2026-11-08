"""Build identity, shared by application, packaging and updater."""
import json
from pathlib import Path

IDENTITY = json.loads(Path(__file__).with_name("release.json").read_text(encoding="utf-8"))
VERSION = IDENTITY["version"]
PRODUCT_ID = IDENTITY["product_id"]
REPOSITORY = IDENTITY["repository"]
