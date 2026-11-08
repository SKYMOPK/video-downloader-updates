"""External updater: verify, stage on the same volume, swap and health-check."""
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from .storage import DATA, atomic_json, read_json
from .update_protocol import extract_package, load_manifest, sha256, version_tuple, long_path


def wait_for_parent(pid, timeout=120, cancel_path=None):
    if os.name != "nt":
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # Already exited.
            return
        raise OSError("無法等待 App 結束，已取消更新")
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel_path and cancel_path.exists(): raise InterruptedError("已取消安裝更新")
            if kernel.WaitForSingleObject(handle, 250) == 0: return
        raise TimeoutError("App 尚未結束，已保留原版本")
    finally:
        kernel.CloseHandle(handle)


def validate_job_path(path):
    path = Path(path).resolve()
    base = (DATA / "app-updates").resolve()
    if path.name != "job.json" or path.parent.parent != base or not re.fullmatch(r"[a-f0-9]{32}", path.parent.name):
        raise ValueError("更新工作位置不正確")
    return path


def is_link(path):
    return path.is_symlink() or path.is_junction()


def preserve_user_files(old, stage, manifest):
    """Uninstaller and user-created files survive; obsolete managed files do not."""
    managed = set(manifest["files"]) | {"app-manifest.json"}
    for path in old.rglob("*"):
        if is_link(path):
            raise ValueError("App 資料夾內有連結，請先移出後再更新")
        if not path.is_file():
            continue
        relative = path.relative_to(old).as_posix()
        if relative in managed:
            continue
        destination = stage / relative
        if destination.exists():
            raise ValueError("更新檔與自建檔案同名，已停止以避免覆蓋")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(long_path(path), long_path(destination))


def launch_app(target, job=None):
    args = [str(target / "VideoDownloader.exe")]
    if job:
        args += ["--update-job", str(job)]
    return subprocess.Popen(args, cwd=str(target), creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def wait_for_health(process, job, version, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = read_json(job.parent / "health.json", {})
        if health.get("version") == version and health.get("job") == job.parent.name:
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.25)
    return False


def apply_job(job_path):
    job_path = validate_job_path(job_path)
    job = read_json(job_path, {})
    target = Path(job["target"]).resolve()
    if target == target.parent or is_link(target) or not target.is_dir():
        raise ValueError("App 安裝位置不正確")
    old_manifest = load_manifest(target)
    if version_tuple(job["version"]) <= version_tuple(old_manifest["version"]):
        raise ValueError("更新版本必須高於目前版本")
    package = job_path.parent / "update.zip"
    stage = target.parent / (target.name + ".new-" + job_path.parent.name)
    backup = target.parent / (target.name + ".previous-" + job_path.parent.name)
    if stage.exists() or backup.exists():
        raise ValueError("已有相同更新工作，請重新下載更新")
    swapped = False
    parent_exited = False
    process = None
    report = {"version": job["version"], "previous": old_manifest["version"], "state": "preparing"}
    report_path = job_path.parent / "result.json"
    atomic_json(report_path, report)
    try:
        if sha256(package) != job["sha256"]:
            raise ValueError("更新包在安裝前驗證失敗")
        if shutil.disk_usage(target.parent).free < 2 * package.stat().st_size + 1024 ** 3:
            raise OSError("安裝位置空間不足，請至少保留約 1.5 GB 可用空間")
        extract_package(package, stage, job["version"])
        if (job_path.parent / "cancel").exists(): raise InterruptedError("已取消安裝更新")
        report["state"] = "waiting_for_exit"
        atomic_json(report_path, report)
        # Do not touch the live installation until the previous process exits.
        wait_for_parent(int(job["pid"]), cancel_path=job_path.parent / "cancel")
        parent_exited = True
        if (job_path.parent / "cancel").exists(): raise InterruptedError("已取消安裝更新")
        preserve_user_files(target, stage, old_manifest)
        report["state"] = "swapping"
        atomic_json(report_path, report)
        target.rename(backup)
        try:
            stage.rename(target)
        except Exception:
            backup.rename(target)
            raise
        swapped = True
        report["state"] = "checking_startup"
        atomic_json(report_path, report)
        process = launch_app(target, job_path)
        if not wait_for_health(process, job_path, job["version"]):
            raise RuntimeError("新版未通過啟動檢查")
        report.update(state="completed", backup=str(backup))
        atomic_json(report_path, report)
        # Keep the complete previous installation for recovery. Never delete user files.
        return True
    except Exception as exc:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        if swapped:
            target.rename(stage)
            backup.rename(target)
        report.update(state="rolled_back" if swapped else "failed", error=str(exc))
        atomic_json(report_path, report)
        if parent_exited: launch_app(target)
        return False
    finally:
        # This path is generated above, in the verified installation's parent.
        if stage.is_dir() and stage.parent == target.parent and stage.name == target.name + ".new-" + job_path.parent.name:
            shutil.rmtree(long_path(stage), ignore_errors=True)


def signal_health(job_path, version, executable):
    path = validate_job_path(job_path)
    job = read_json(path, {})
    if Path(job.get("target", "")).resolve() != Path(executable).resolve().parent or job.get("version") != version:
        raise ValueError("更新啟動資訊不一致")
    atomic_json(path.parent / "health.json", {"job": path.parent.name, "version": version})


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError("更新程式需要有效的工作資訊")
        return 0 if apply_job(sys.argv[1]) else 1
    except Exception as exc:
        # Never execute a fallback path from an invalid job.
        try:
            path = validate_job_path(sys.argv[1])
            atomic_json(path.parent / "result.json", {"state": "failed", "error": str(exc)})
        except Exception:
            pass
        return 1
