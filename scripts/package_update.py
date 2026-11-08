"""Build a complete, versioned update package from the packaged application."""
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.release import VERSION, PRODUCT_ID
from app.update_protocol import sha256


def package_update(root=ROOT):
    application = root / "dist/VideoDownloader"
    files = sorted(p for p in application.rglob("*") if p.is_file() and p.name != "app-manifest.json")
    manifest = {"product_id": PRODUCT_ID, "version": VERSION,
                "files": {p.relative_to(application).as_posix(): sha256(p) for p in files}}
    (application / "app-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    target = root / f"dist/VideoDownloader-{VERSION}-win64-update.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for path in files + [application / "app-manifest.json"]:
            archive.write(path, "VideoDownloader/" + path.relative_to(application).as_posix())
    print(json.dumps({"update_package": target.name, "files": len(files), "bytes": target.stat().st_size, "sha256": sha256(target)}))
    return target


if __name__ == "__main__":
    package_update()
