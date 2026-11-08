"""Explicit, staged updates from official yt-dlp GitHub releases."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

from PySide6.QtCore import QThread, Signal
from .storage import DATA, atomic_json, read_json


def get(url, limit=2_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": "VideoDownloader/0.1", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("更新資料超過允許大小")
        return data


class UpdateWorker(QThread):
    result = Signal(bool, str, str)

    def __init__(self, install=False, expected="", parent=None):
        super().__init__(parent)
        self.install, self.expected = install, expected

    def run(self):
        staging = None
        try:
            release = json.loads(get("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"))
            version = release["tag_name"]
            if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(?:\.\d+)?", version):
                raise ValueError("官方版本識別格式不符，已停止更新")
            if not self.install:
                self.result.emit(True, version, "官方穩定版：" + version)
                return
            if version != self.expected:
                raise ValueError("官方版本已變更，請重新檢查更新並確認")
            asset = next(a for a in release["assets"] if a["name"] == "yt-dlp.exe")
            url = asset["browser_download_url"]
            if url != f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/yt-dlp.exe":
                raise ValueError("更新來源不符官方發行位置")
            sums = get(f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/SHA2-256SUMS").decode()
            expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip("*") == "yt-dlp.exe")
            data = get(url, 80_000_000)
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected or (asset.get("digest") and asset["digest"] != "sha256:" + digest):
                raise ValueError("更新檔完整性驗證失敗")
            target = DATA / "cores" / version
            staging = DATA / "cores" / (version + ".staging")
            staging.mkdir(parents=True, exist_ok=True)
            exe = staging / "yt-dlp.exe"
            exe.write_bytes(data)
            result = subprocess.run([str(exe), "--ignore-config", "--no-plugin-dirs", "--version"], capture_output=True, timeout=30,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode or result.stdout.decode().strip() != version:
                raise ValueError("新核心啟動檢查失敗，已保留既有版本")
            atomic_json(staging / "provenance.json", {"version": version, "source": url, "sha256": digest,
                        "verification": "GitHub HTTPS + official release SHA256; not a detached signature verification"})
            if not target.exists():
                staging.rename(target)
                staging = None
            elif not (target/"yt-dlp.exe").is_file() or hashlib.sha256((target/"yt-dlp.exe").read_bytes()).hexdigest()!=digest:
                raise ValueError("已存在的核心版本校驗不符，未切換；請先回復隨附核心並重新安裝 App")
            old = read_json(DATA / "core-active.json", {})
            atomic_json(DATA / "core-previous.json", old)
            atomic_json(DATA / "core-active.json", {"version": version})
            self.result.emit(True, version, "核心已更新。新的任務將使用此版本，可回復隨附版本")
        except Exception as exc:
            self.result.emit(False, "", "更新未完成，既有版本仍可使用：" + str(exc))
        finally:
            if staging and staging.is_dir():
                shutil.rmtree(staging, ignore_errors=True)
