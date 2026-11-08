"""Version and complete-package validation. No Qt or executable loading."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

PRODUCT_ID = "0A065A63-454A-44CC-A06B-3B22BDCE2F18"
MAX_DOWNLOAD = 1024 ** 3
MAX_EXPANDED = 3 * 1024 ** 3
MAX_FILES = 12000


def long_path(path):
    path = Path(path).absolute()
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("正式版本號格式不正確")
    return tuple(map(int, value.lstrip("v").split(".")))


def sha256(path):
    result = hashlib.sha256()
    with long_path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b""):
            result.update(chunk)
    return result.hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError("更新包含有不安全的路徑")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") or p.endswith((".", " ")) for p in value.split("/")):
        raise ValueError("更新包含有不安全的路徑")
    if any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part) for part in path.parts):
        raise ValueError("更新包含有 Windows 保留檔名")
    return path


def parse_release(raw, repository, current):
    """Accept only a stable release's versioned, repository-bound asset."""
    if not isinstance(raw, dict) or raw.get("draft") or raw.get("prerelease"):
        raise ValueError("更新來源不是正式版本")
    tag = raw.get("tag_name", "")
    version = tag.removeprefix("v")
    if version_tuple(version) <= version_tuple(current):
        return None
    name = f"VideoDownloader-{version}-win64-update.zip"
    assets = [a for a in raw.get("assets", []) if a.get("name") == name]
    if len(assets) != 1:
        raise ValueError("新版尚未提供完整的 Windows 更新包，請稍後再試")
    asset = assets[0]
    url = f"https://github.com/{repository}/releases/download/{tag}/{name}"
    if asset.get("browser_download_url") != url or asset.get("state", "uploaded") != "uploaded":
        raise ValueError("更新檔不在指定的 GitHub 發布位置")
    digest = asset.get("digest", "")
    size = asset.get("size")
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
        raise ValueError("更新檔缺少 SHA256 驗證資訊")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_DOWNLOAD:
        raise ValueError("更新檔大小超過允許範圍")
    return {"version": version, "url": url, "sha256": digest[7:].lower(), "size": size,
            "notes": str(raw.get("body") or "此版本未提供更新說明。")[:16000]}


def load_manifest(root):
    path = long_path(root) / "app-manifest.json"
    if path.stat().st_size > 4_000_000:
        raise ValueError("版本清單過大")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("product_id") != PRODUCT_ID:
        raise ValueError("更新包不是這個 App 的正式檔案")
    version_tuple(value["version"])
    files = value.get("files", {})
    if not isinstance(files, dict) or not 2 <= len(files) <= MAX_FILES:
        raise ValueError("更新包檔案清單不完整")
    for name, digest in files.items():
        safe_relative(name)
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("檔案驗證資訊不正確")
    if "VideoDownloader.exe" not in files or "_internal/app/release.json" not in files:
        raise ValueError("更新包缺少主要程式")
    return value


def extract_package(archive, target, expected_version):
    target = long_path(target)
    target.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > MAX_FILES + 500 or sum(f.file_size for f in entries) > MAX_EXPANDED:
            raise ValueError("更新包展開大小超過允許範圍")
        seen = set()
        for entry in entries:
            relative = safe_relative(entry.filename.rstrip("/"))
            if not relative.parts or relative.parts[0] != "VideoDownloader":
                raise ValueError("更新包資料夾不正確")
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or entry.flag_bits & 1:
                raise ValueError("更新包含有不支援的連結或加密檔案")
            if entry.is_dir():
                continue
            parts = relative.parts[1:]
            if not parts or str(PurePosixPath(*parts)).casefold() in seen:
                raise ValueError("更新包含有重複檔名")
            seen.add(str(PurePosixPath(*parts)).casefold())
            destination = target.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, destination.open("xb") as output:
                while chunk := source.read(1024 ** 2):
                    output.write(chunk)
    manifest = load_manifest(target)
    if manifest["version"] != expected_version:
        raise ValueError("更新包與已確認的版本不同")
    expected = set(manifest["files"]) | {"app-manifest.json"}
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    if actual != expected:
        raise ValueError("更新包的檔案清單不一致")
    for name, digest in manifest["files"].items():
        if sha256(target / name) != digest:
            raise ValueError("更新包內的檔案驗證失敗")
    identity = json.loads((target / "_internal/app/release.json").read_text(encoding="utf-8"))
    if identity.get("product_id") != PRODUCT_ID or identity.get("version") != expected_version:
        raise ValueError("程式版本識別不一致")
    return manifest
