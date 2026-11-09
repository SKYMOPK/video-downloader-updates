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
office = json.loads((root / 'tools/office-manifest.json').read_text())
engine = root / 'tools/office/program/soffice.com'
with engine.open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest() != office['soffice_sha256']:
        raise SystemExit('文件轉換引擎完整性驗證失敗')
print('文件轉換引擎與官方安裝包紀錄相符')
with (root/'tools/office-runtime.zip').open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=office['runtime_sha256']:
        raise SystemExit('文件轉換引擎封裝驗證失敗')
