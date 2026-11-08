import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "tools" / "manifest.json").read_text())
for entry in manifest:
    path = root / "tools" / entry["name"]
    if path.parent != root / "tools" or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit("依賴驗證失敗：" + entry["name"])
print("所有隨附工具 SHA256 與建置清單相符")
