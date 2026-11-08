"""Real Windows EXEs: complete-package replacement and startup-failure rollback.

Future-version identities are local acceptance fixtures, never published releases.
"""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import atomic_json, read_json
from app.update_protocol import sha256

WORK = ROOT / ("work-update-it-" + uuid.uuid4().hex[:8])
WORK.mkdir(exist_ok=True)
TARGET = WORK / "App"
DATA = WORK / "data"
DATA.mkdir(exist_ok=True)
environment = dict(os.environ, VD_DATA_DIR=str(DATA), VD_DISABLE_APP_UPDATE_CHECK="1")


def close_test_app():
    pids = set()
    for process in psutil.process_iter(["pid", "exe"]):
        if process.info["exe"] and Path(process.info["exe"]).resolve() == (TARGET / "VideoDownloader.exe").resolve():
            pids.add(process.info["pid"])
    from ctypes import wintypes
    user = ctypes.WinDLL("user32")
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    @callback_type
    def close(hwnd, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids: user.PostMessageW(hwnd, 0x0010, 0, 0)
        return True
    user.EnumWindows(close, 0)
    for pid in pids:
        try: psutil.Process(pid).wait(timeout=15)
        except psutil.NoSuchProcess: pass


def make_job(version, broken=False):
    directory = DATA / "app-updates" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    manifest = read_json(TARGET / "app-manifest.json", {})
    identity_path = "_internal/app/release.json"
    identity = read_json(TARGET / identity_path, {}) | {"version": version}
    identity_bytes = json.dumps(identity).encode("utf-8")
    import hashlib
    manifest["version"] = version
    manifest["files"][identity_path] = hashlib.sha256(identity_bytes).hexdigest()
    if broken: manifest["files"]["VideoDownloader.exe"] = hashlib.sha256(b"MZ intentionally broken startup fixture").hexdigest()
    with zipfile.ZipFile(directory / "update.zip", "w", zipfile.ZIP_STORED) as archive:
        for name in manifest["files"]:
            if name == identity_path:
                archive.writestr("VideoDownloader/" + name, identity_bytes)
            elif broken and name == "VideoDownloader.exe":
                archive.writestr("VideoDownloader/" + name, b"MZ intentionally broken startup fixture")
            else:
                archive.write(TARGET / name, "VideoDownloader/" + name)
        archive.writestr("VideoDownloader/app-manifest.json", json.dumps(manifest).encode("utf-8"))
    parent = subprocess.Popen([str(TARGET / "VideoDownloader.exe"), "--quit-after", "4"], env=environment, cwd=TARGET)
    atomic_json(directory / "job.json", {"pid": parent.pid, "target": str(TARGET), "version": version, "sha256": sha256(directory / "update.zip")})
    helper = directory / "app-updater.exe"
    shutil.copy2(ROOT / "build/updater-dist/app-updater.exe", helper)
    process = subprocess.run([str(helper), str(directory / "job.json")], env=environment, timeout=180, cwd=directory)
    parent.wait(timeout=15)
    close_test_app()
    result = read_json(directory / "result.json", {})
    assert (TARGET / "使用者文件.txt").read_text(encoding="utf-8") == "更新必須保留此檔案"
    assert read_json(DATA / "settings.json", {})["notifications"] is False
    assert (DATA / "keep.txt").read_text() == "user data"
    return {"helper_exit": process.returncode, "result": result, "current": read_json(TARGET / "app-manifest.json", {})["version"]}


if __name__ == "__main__":
    if TARGET.exists(): raise SystemExit("Acceptance directory already exists; choose a fresh work directory before rerunning.")
    shutil.copytree(ROOT / "dist/VideoDownloader", TARGET)
    (TARGET / "使用者文件.txt").write_text("更新必須保留此檔案", encoding="utf-8")
    atomic_json(DATA / "settings.json", {"folder": str(WORK / "downloads"), "notifications": False})
    (DATA / "keep.txt").write_text("user data")
    good = make_job("0.2.1")
    assert good["helper_exit"] == 0 and good["result"]["state"] == "completed" and good["current"] == "0.2.1", good
    bad = make_job("0.2.2", broken=True)
    assert bad["helper_exit"] == 1 and bad["result"]["state"] == "rolled_back" and bad["current"] == "0.2.1", bad
    report = {"real_windows_executables": True, "local_future_version_fixture": True, "successful_update": good, "failed_startup_rollback": bad,
              "user_files_preserved": True, "settings_preserved": True}
    atomic_json(ROOT / "evidence/app-update-integration.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
