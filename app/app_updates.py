"""Whole-application updates, independent of the yt-dlp core updater."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot
from .release import VERSION, REPOSITORY, PRODUCT_ID
from .storage import DATA, ROOT, atomic_json, read_json
from .update_protocol import MAX_DOWNLOAD, parse_release, sha256, version_tuple

ALLOWED_HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def check_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("更新連線來源不正確")


class GithubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def open_url(url):
    check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": f"VideoDownloader/{VERSION}", "Accept": "application/vnd.github+json"})
    return urllib.request.build_opener(GithubRedirect()).open(request, timeout=15)


class AppUpdateWorker(QThread):
    result = Signal(bool, object, str)
    progress = Signal(int)

    def __init__(self, release=None, parent=None):
        super().__init__(parent)
        self.release = release

    def run(self):
        directory = None
        try:
            if self.release is None:
                with open_url(f"https://api.github.com/repos/{REPOSITORY}/releases/latest") as response:
                    payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError("更新資訊超過允許大小")
                raw = json.loads(payload)
                release = parse_release(raw, REPOSITORY, VERSION)
                if self.isInterruptionRequested(): raise InterruptedError()
                self.result.emit(True, {"release": release, "raw": raw}, "發現新版本" if release else "目前已是最新版本")
                return
            release = self.release
            directory = DATA / "app-updates" / uuid.uuid4().hex
            directory.mkdir(parents=True)
            atomic_json(directory / "download.json", {"product_id": PRODUCT_ID, "version": release["version"], "created": time.time()})
            if shutil.disk_usage(directory).free < release["size"] + 128 * 1024 ** 2:
                raise OSError("下載更新的空間不足")
            digest = hashlib.sha256()
            total = 0
            start = time.monotonic()
            with open_url(release["url"]) as response, (directory / "update.part").open("xb") as output:
                while True:
                    if self.isInterruptionRequested(): raise InterruptedError()
                    if time.monotonic() - start > 1800: raise TimeoutError("更新下載逾時")
                    chunk = response.read(256 * 1024)
                    if not chunk: break
                    total += len(chunk)
                    if total > release["size"] or total > MAX_DOWNLOAD:
                        raise ValueError("下載大小與發布資訊不符")
                    output.write(chunk)
                    digest.update(chunk)
                    self.progress.emit(min(99, int(total * 100 / release["size"])))
            if self.isInterruptionRequested(): raise InterruptedError()
            if total != release["size"] or digest.hexdigest() != release["sha256"]:
                raise ValueError("更新檔完整性驗證失敗，已保留目前版本")
            (directory / "update.part").rename(directory / "update.zip")
            self.progress.emit(100)
            self.result.emit(True, {"directory": str(directory)}, "更新已下載並驗證")
            directory = None
        except InterruptedError:
            self.result.emit(False, {}, "已取消更新，現有版本仍可使用")
        except urllib.error.HTTPError as exc:
            message = "尚未發布正式版本，請稍後再檢查" if exc.code == 404 else ("GitHub 暫時限制檢查次數，請稍後再試" if exc.code in (403, 429) else "更新服務暫時無法使用，請稍後再試")
            self.result.emit(False, {}, message)
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ValueError, OSError)) and not isinstance(exc, urllib.error.URLError) else "無法連線到更新服務，請檢查網路後重試"
            self.result.emit(False, {}, message)
        finally:
            if directory and directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)


class AppUpdates(QObject):
    changed = Signal()
    prompt = Signal()
    installReady = Signal()
    settled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.release = None
        self.directory = None
        self._state, self._message, self._progress = "idle", "檢查整個 App 的正式版本更新", -1
        self._pending = False
        self.helper_process = None
        self.helper_timer = QTimer(self)
        self.helper_timer.setInterval(200)
        self.helper_timer.timeout.connect(self._check_helper)
        self.cache_path = DATA / "app-update-state.json"
        cache = read_json(self.cache_path, {})
        self.cache = cache if isinstance(cache, dict) else {}
        self._restore_release()

    def _restore_release(self):
        try:
            raw = self.cache.get("release")
            if raw:
                self.release = parse_release(raw, REPOSITORY, VERSION)
                if self.release:
                    self._state, self._message = "available", "有可用的 App 更新"
        except (ValueError, TypeError, KeyError):
            self.release = None

    @Property(str, constant=True)
    def currentVersion(self): return VERSION
    @Property(str, constant=True)
    def repository(self): return REPOSITORY
    @Property(str, notify=changed)
    def state(self): return self._state
    @Property(str, notify=changed)
    def status(self): return self._message
    @Property(int, notify=changed)
    def progress(self): return self._progress
    @Property(bool, notify=changed)
    def available(self): return self.release is not None
    @Property(str, notify=changed)
    def latestVersion(self): return self.release["version"] if self.release else ""
    @Property(str, notify=changed)
    def notes(self): return self.release["notes"] if self.release else ""
    @Property(str, notify=changed)
    def downloadSize(self): return f"{self.release['size'] / 1024 ** 2:.1f} MB" if self.release else ""
    @Property(bool, notify=changed)
    def busy(self): return self.worker is not None or self.helper_process is not None
    @Property(bool, notify=changed)
    def installPending(self): return self._pending
    @Property(bool, notify=changed)
    def autoCheck(self): return self.cache.get("auto_check", True) is not False
    @Property(bool, notify=changed)
    def showPrompts(self): return self.cache.get("show_prompts", True) is not False

    def save(self):
        try:
            atomic_json(self.cache_path, self.cache)
        except OSError:
            self._message = "無法保存更新偏好，請確認本機資料夾空間與權限"

    @Slot(bool)
    def setAutoCheck(self, value):
        self.cache["auto_check"] = bool(value)
        self.save()
        self.changed.emit()

    @Slot(bool)
    def setShowPrompts(self, value):
        self.cache["show_prompts"] = bool(value)
        self.save()
        self.changed.emit()

    def _prompt_once(self):
        if self.available and self.showPrompts and self.cache.get("notified") != self.latestVersion:
            self.cache["notified"] = self.latestVersion
            self.save()
            self.prompt.emit()

    @Slot()
    def startup(self):
        if os.environ.get("VD_DISABLE_APP_UPDATE_CHECK") == "1": return
        self.clean_cache()
        # Show any helper failure in the next launch, without exposing local paths.
        results = sorted((DATA / "app-updates").glob("*/result.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if results:
            result = read_json(results[0], {})
            if result.get("state") in ("rolled_back", "failed"):
                self._message = "上次更新未完成，已保留或回復原版本。可重新下載更新。"
                self.changed.emit()
        if not self.autoCheck: return
        self._prompt_once()
        last = self.cache.get("checked_at", 0)
        if isinstance(last, (float, int)) and 0 <= time.time() - last < 6 * 3600:
            return
        self.check(False)

    def clean_cache(self):
        """Expire only known cache payloads, leaving audit records and user files."""
        for marker in (DATA / "app-updates").glob("*/download.json"):
            info = read_json(marker, {})
            created = info.get("created") if isinstance(info, dict) else None
            if not isinstance(info, dict) or info.get("product_id") != PRODUCT_ID or not isinstance(created, (int, float)) or time.time() - created < 7 * 86400:
                continue
            if self.directory and marker.parent == self.directory: continue
            try:
                for name in ("update.zip", "update.part", "app-updater.exe"):
                    (marker.parent / name).unlink(missing_ok=True)
            except OSError:
                pass

    @Slot()
    def checkNow(self): self.check(True)

    def check(self, manual=False):
        if self.busy or self._pending: return
        self._state, self._message = "checking", "正在檢查 App 最新版本…"
        worker = AppUpdateWorker(parent=self)
        self.worker = worker
        def result(ok, data, message):
            self._message = message
            if ok:
                self.release = data["release"]
                self.cache.update(release=data["raw"], checked_at=time.time())
                self.save()
                self._state = "available" if self.available else "current"
                if not manual: self._prompt_once()
            else:
                self._state = "available" if self.available else "error"
            self.changed.emit()
        self._connect_worker(worker, result)

    def _connect_worker(self, worker, callback):
        worker.result.connect(callback)
        def finished():
            self.worker = None
            worker.deleteLater()
            self.changed.emit()
            self.settled.emit()
        worker.finished.connect(finished)
        self.changed.emit()
        worker.start()

    @Slot()
    def download(self):
        if self.busy or not self.release or self._pending: return
        self.directory = None
        self._pending = True
        self._progress, self._state, self._message = 0, "downloading", "正在下載整個 App 更新…"
        worker = AppUpdateWorker(dict(self.release), self)
        self.worker = worker
        worker.progress.connect(self._on_progress)
        def result(ok, data, message):
            self._message = message
            if ok:
                self.directory = Path(data["directory"])
                self._state = "ready"
            else:
                self._state = "available"
                self._pending = False
            self.changed.emit()
        self._connect_worker(worker, result)

    def _on_progress(self, value):
        self._progress = value
        self.changed.emit()

    @Slot()
    def cancel(self):
        self._pending = False
        if self.helper_process and self.directory:
            (self.directory / "cancel").touch()
            self._message = "正在取消更新…"
        if self.worker:
            self._message = "正在取消更新…"
            self.worker.requestInterruption()
        elif self.directory and not self.helper_process:
            self._state, self._message = "available", "已取消安裝，現有版本仍可使用"
            self.directory = None
        self.changed.emit()

    def launch_install(self):
        if self.worker or not self._pending or not self.directory or not self.release:
            return False
        if not getattr(sys, "frozen", False):
            self._pending = False
            self._message = "原始碼開發模式不會覆寫專案，請使用封裝版測試安裝更新"
            self.changed.emit()
            return False
        try:
            target = Path(sys.executable).resolve().parent
            # Validate ownership before launching an external process.
            from .update_protocol import load_manifest
            manifest = load_manifest(target)
            if manifest["version"] != VERSION:
                raise ValueError("本機版本識別不一致，請重新安裝 App")
            if sha256(self.directory / "update.zip") != self.release["sha256"]:
                raise ValueError("更新檔驗證失敗，請重新下載")
            helper = ROOT / "tools/app-updater.exe"
            if not helper.is_file(): raise ValueError("更新元件遺失，請重新安裝 App")
            copied = self.directory / "app-updater.exe"
            shutil.copy2(helper, copied)
            job = self.directory / "job.json"
            atomic_json(job, {"pid": os.getpid(), "target": str(target), "version": self.latestVersion,
                              "sha256": self.release["sha256"]})
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self.helper_process = subprocess.Popen([str(copied), str(job)], cwd=str(self.directory), creationflags=flags)
            self._state, self._message = "preparing_install", "正在驗證並準備安裝更新…"
            self.helper_timer.start()
            self.changed.emit()
            return True
        except Exception:
            self._pending = False
            self._state, self._message = "available", "無法啟動更新安裝，現有版本仍可使用。請重新下載或重新安裝。"
            self.changed.emit()
            return False

    def _check_helper(self):
        if not self.helper_process or not self.directory: return
        result = read_json(self.directory / "result.json", {})
        if result.get("state") == "waiting_for_exit" and self._pending:
            self.helper_timer.stop()
            self._state, self._message = "installing", "正在關閉 App 並安裝更新…"
            self.changed.emit()
            self.installReady.emit()
        elif self.helper_process.poll() is not None:
            self.helper_timer.stop()
            self.helper_process = None
            self._pending = False
            self._state = "available"
            self._message = "更新準備未完成，現有版本仍可使用。可重新下載後再試。"
            self.changed.emit()
            self.settled.emit()
