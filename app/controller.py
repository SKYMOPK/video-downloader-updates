import json
from pathlib import Path
import re
import shutil
import time
import uuid

from PySide6.QtCore import (QAbstractListModel, QModelIndex, Qt, QObject, Property, Signal, Slot, QUrl, QTimer)
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import QFileDialog, QSystemTrayIcon

from .storage import DATA, ROOT, atomic_json, read_json, load_settings, tool
from .formats import normalize_url, normalize, plan, recommended_index, codec_name, size_text, video_choices, UserError
from .engine import Download, core_args
from .process import ManagedProcess
from .updater import UpdateWorker
from .app_updates import AppUpdates
from .release import VERSION

STATES = {"queued": "等待中", "parsing": "解析中", "downloading": "下載中", "merging": "合併／封裝中",
          "converting": "轉換中", "verifying": "驗證中", "completed": "已完成", "failed": "失敗",
          "cancelling": "停止中", "cancelled": "已取消", "recoverable": "待恢復", "waiting_processing": "等待轉換"}
ACTIVE = {"queued", "parsing", "downloading", "merging", "converting", "verifying", "cancelling", "waiting_processing"}


def redact(text):
    text = re.sub(r"https?://[^\s\"']+", "[來源網址已隱藏]", str(text))
    text = text.replace(str(Path.home()), "[使用者目錄]")
    return text[-12000:]


class TaskModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []

    def roleNames(self):
        return {Qt.ItemDataRole.UserRole + 1: b"item"}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items):
            return None
        task = self.items[index.row()]
        return task | {"stateLabel": STATES.get(task["state"], task["state"]), "active": task["state"] in ACTIVE}

    def add(self, task):
        self.beginInsertRows(QModelIndex(), 0, 0)
        self.items.insert(0, task)
        self.endInsertRows()

    def refresh(self, task):
        for i, item in enumerate(self.items):
            if item["id"] == task["id"]:
                index = self.index(i, 0)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.UserRole + 1])
                break


class Controller(QObject):
    changed = Signal()
    message = Signal(str)
    shutdownReady = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        DATA.mkdir(parents=True, exist_ok=True)
        self._settings = load_settings()
        self._media, self._busy, self._error = {}, False, ""
        self._url, self.parser, self.parse_round = "", None, 0
        self._mode = self._settings["mode"]
        self._video_index, self._audio_index = 0, 0
        self._container, self._audio_format, self._bitrate = "mp4", "original", "192"
        self.model = TaskModel(self)
        stored = read_json(DATA / "tasks.json", [])
        for task in reversed(stored if isinstance(stored, list) else []):
            if not isinstance(task, dict) or not all(k in task for k in ("id", "url", "options", "plan", "title", "folder", "state")):
                continue
            if task["state"] in ACTIVE:
                task["state"] = "recoverable"
                task["detail"] = "上次未完成，請選擇重試"
            self.model.add(task)
        self.runners, self.checkers, self.update_worker = {}, [], None
        self.processing_owner, self.processing_waiters = None, []
        self.closing, self._update_busy, self._latest = False, False, ""
        self._update_message = "從官方來源檢查 yt-dlp 穩定版；更新前會再次確認"
        self._versions = {name: "檢查中" for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")}
        self._dependency_ok = {name: False for name in self._versions}
        self._fallback_attempted=False
        self.style_hints = QGuiApplication.styleHints()
        self.accessibility_hints = self.style_hints.accessibility()
        self.accessibility_hints.motionPreferenceChanged.connect(lambda *_: self.changed.emit())
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(self.persist)
        self.tray = QSystemTrayIcon(QIcon(str(ROOT / "assets" / "app.ico")), self)
        self.app_updates = AppUpdates(self)
        self.app_updates.changed.connect(self.changed.emit)
        self.app_updates.installReady.connect(self._quit_for_update)
        self.app_updates.settled.connect(self._maybe_finish_shutdown)
        self.app_update_timer = QTimer(self)
        self.app_update_timer.setInterval(1000)
        self.app_update_timer.timeout.connect(self._try_app_install)
        self.app_update_timer.start()
        QTimer.singleShot(100, self.check_dependencies)
        QTimer.singleShot(1500,lambda:self.cleanTemp(True))

    @Property("QVariantMap", notify=changed)
    def settings(self): return self._settings
    @Property(QObject, constant=True)
    def appUpdates(self): return self.app_updates
    @Property("QVariantMap", notify=changed)
    def media(self): return self._media
    @Property(bool, notify=changed)
    def busy(self): return self._busy
    @Property(str, notify=changed)
    def error(self): return self._error
    @Property(str, notify=changed)
    def mode(self): return self._mode
    @Property(str, notify=changed)
    def parsedUrl(self): return self._url
    @Property(int, notify=changed)
    def videoIndex(self): return self._video_index
    @Property(int, notify=changed)
    def audioIndex(self): return self._audio_index
    @Property(str, notify=changed)
    def container(self): return self._container
    @Property(str, notify=changed)
    def audioFormat(self): return self._audio_format
    @Property(str, notify=changed)
    def bitrate(self): return self._bitrate
    @Property(QObject, constant=True)
    def tasks(self): return self.model
    @Property(int, notify=changed)
    def taskCount(self): return len(self.model.items)
    @Property(int, notify=changed)
    def activeCount(self): return sum(t["state"] in ACTIVE for t in self.model.items)
    @Property("QVariantMap", notify=changed)
    def versions(self): return self._versions
    @Property(bool, notify=changed)
    def reducedMotion(self):
        return self._settings["reduceMotion"] or self.accessibility_hints.motionPreference().value == 1
    @Property(bool, notify=changed)
    def updateBusy(self): return self._update_busy
    @Property(str, notify=changed)
    def latestVersion(self): return self._latest
    @Property(str, notify=changed)
    def updateMessage(self): return self._update_message
    @Property("QVariantList", notify=changed)
    def videoOptions(self): return [f["label"] for f in self.quality_choices()]
    def quality_choices(self): return video_choices(self._media.get("videos", []), self._container)
    @Property(int, notify=changed)
    def qualityIndex(self):
        videos = self._media.get("videos", [])
        if not 0 <= self._video_index < len(videos): return -1
        selected = videos[self._video_index]
        return next((i for i, choice in enumerate(self.quality_choices())
                     if (videos[choice["index"]]["height"], round(videos[choice["index"]]["fps"]))
                     == (selected["height"], round(selected["fps"]))), -1)
    @Property("QVariantList", notify=changed)
    def audioOptions(self):
        return [f"{codec_name(f['acodec'])} · 約 {f['abr']:.0f} kbps" + (f" · {f['language']}" if f["language"] else "") + (f" · {f['channels']} 聲道" if f.get("channels") else "") + (" · 動態範圍壓縮" if "DRC" in f["note"] else "") for f in self._media.get("audios", [])]

    def current_plan(self):
        return plan(self._media, self._mode, self._video_index, self._container, self._audio_format, self._bitrate, self._audio_index)

    @Property(str, notify=changed)
    def summary(self):
        if not self._media: return "解析影片後，選擇需要的規格"
        try: return self.current_plan()["summary"]
        except UserError as exc: return str(exc)

    @Property(bool, notify=changed)
    def canDownload(self):
        if self.app_updates.installPending: return False
        if not self._media or self._busy: return False
        if not all(self._dependency_ok.values()) or self._update_busy: return False
        try:
            self.current_plan()
            return True
        except (UserError, ValueError): return False

    @Property(bool, notify=changed)
    def needsConversion(self):
        try: return self.current_plan()["transcode"]
        except (UserError, ValueError): return False

    @Property(str, notify=changed)
    def sourceDetail(self):
        if not self._media: return ""
        audios = self._media.get("audios", [])
        audio = audios[self._audio_index] if audios and self._audio_index < len(audios) else None
        return (f"來源音訊：{codec_name(audio['acodec'])} · 約 {audio['abr']:.0f} kbps。提高輸出位元率不會提升來源品質。" if audio else "來源音訊資訊不可用")

    @Property(str, notify=changed)
    def sourceSize(self):
        try:
            audio = self._media["audios"][self._audio_index]
            if self._mode == "audio": return "來源預估下載量：" + size_text(audio["size"])
            video = self._media["videos"][self._video_index]
            size = video["size"] + (audio["size"] if video["acodec"] in (None, "none") else 0)
            if not video["size"] or (video["acodec"] in (None,"none") and not audio["size"]): size = 0
            return "來源預估下載量：" + size_text(size) + "；輸出大小依實際處理結果而定"
        except (KeyError, IndexError): return "來源大小未知"

    @Slot(str)
    def parse(self, value):
        if self.app_updates.installPending:
            self.message.emit("App 更新已排程，請完成或取消更新後再加入新工作")
            return
        if self._update_busy:
            self.message.emit("請等核心更新完成後再解析")
            return
        try:
            url = normalize_url(value)
        except (UserError, ValueError) as exc:
            self.parse_round += 1
            if self.parser: self.parser.cancel()
            self.parser, self._busy, self._media = None, False, {}
            self._error = str(exc)
            self.changed.emit()
            return
        if url == self._url and self._busy: return
        if url == self._url and self._media and not self._error: return
        if "list=" in value:
            self.message.emit("此版本只處理連結中的單部影片，播放清單批次下載尚未開放")
        if self.parser: self.parser.cancel()
        self.parse_round += 1
        generation = self.parse_round
        self._busy, self._media, self._error, self._url = True, {}, "", url
        self.changed.emit()
        parser = ManagedProcess(tool("yt-dlp"), core_args() + ["--skip-download", "--dump-single-json", "--", url], self)
        self.parser = parser
        def parsed(code, output):
            parser.deleteLater()
            if generation != self.parse_round: return
            self.parser, self._busy = None, False
            if code:
                from .formats import classify_error
                self._error = classify_error(output)[0]
                self.last_diagnostic = redact(output)
            else:
                try:
                    raw = next(line for line in reversed(output.splitlines()) if line.startswith("{"))
                    self._media = normalize(json.loads(raw))
                    if "/shorts/" in value: self._media["type"] = "Shorts"
                    self._video_index = recommended_index(self._media["videos"]) if self._settings["strategy"] == "recommended" else 0
                    self._audio_index = 0
                    if self._settings["strategy"] == "recommended":
                        # Prefer AAC in the SAME language as the preferred source track.
                        audios = self._media["audios"]
                        language = audios[0]["language"] if audios else ""
                        self._audio_index = next((i for i, a in enumerate(audios) if a["language"] == language and codec_name(a["acodec"]) == "AAC"), 0)
                    self._container = "mp4" if self._settings["strategy"] == "recommended" else "mkv"
                    if self.needsConversion: self._container = "mkv"
                except (ValueError, StopIteration, UserError, KeyError) as exc:
                    self._error = str(exc) or "無法讀取影片資訊"
            self.changed.emit()
        parser.done.connect(parsed)
        parser.start()

    @Slot(str)
    def inputEdited(self, value):
        try: same = normalize_url(value) == self._url
        except (UserError, ValueError): same = False
        if same: return
        self.parse_round += 1
        if self.parser: self.parser.cancel()
        self.parser, self._busy, self._media, self._error = None, False, {}, ""
        self.changed.emit()

    @Slot()
    def cancelParse(self):
        self.parse_round += 1
        if self.parser: self.parser.cancel()
        self.parser, self._busy = None, False
        self._error = "已停止解析"
        self.changed.emit()

    @Slot(result=str)
    def clipboard(self): return QGuiApplication.clipboard().text().strip()

    @Slot(str, str)
    def select(self, key, value):
        if key == "quality_index":
            try:
                index = int(value)
                choices = self.quality_choices()
                if 0 <= index < len(choices): self._video_index = choices[index]["index"]
            except ValueError: pass
            self.changed.emit()
            return
        quality_index = self.qualityIndex
        allowed = {"mode": ("video", "audio"), "container": ("mp4", "mkv", "webm"),
                   "audio_format": ("original", "mp3", "m4a", "opus", "wav"), "bitrate": ("128", "192", "256", "320")}
        if key in allowed and value in allowed[key]: setattr(self, "_" + key, value)
        elif key in ("video_index", "audio_index"):
            try: setattr(self, "_" + key, max(0, int(value)))
            except ValueError: pass
        if key == "container" and 0 <= quality_index < len(self.quality_choices()):
            self._video_index = self.quality_choices()[quality_index]["index"]
        self.changed.emit()

    @Slot()
    def chooseFolder(self):
        folder = QFileDialog.getExistingDirectory(None, "選擇下載資料夾", self._settings["folder"])
        if folder:
            self._settings["folder"] = folder
            self.save_settings()

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if key == "concurrency": self._settings[key] = max(1, min(3, int(value)))
        elif key in ("notifications", "reduceMotion"): self._settings[key] = bool(value)
        elif key == "mode" and value in ("video", "audio"): self._settings[key] = value
        elif key == "strategy" and value in ("recommended", "best"): self._settings[key] = value
        else: return
        self.save_settings()
        self.schedule()

    def save_settings(self):
        try: atomic_json(DATA / "settings.json", self._settings)
        except OSError: self.message.emit("無法保存設定，請確認本機資料夾權限")
        self.changed.emit()

    @Slot()
    def enqueue(self):
        if not self.canDownload: return
        try:
            p = self.current_plan()
            folder = Path(self._settings["folder"])
            folder.mkdir(parents=True, exist_ok=True)
            options = {"mode": self._mode, "container": self._container, "audio_format": self._audio_format,
                       "bitrate": self._bitrate, "video_id": self._media["videos"][self._video_index]["id"] if self._mode == "video" else "",
                       "audio_id": self._media["audios"][self._audio_index]["id"] if self._media["audios"] else ""}
            duplicate = any(t["state"] in ACTIVE and t["url"] == self._url and t["options"] == options and t["folder"] == str(folder) for t in self.model.items)
            if duplicate:
                self.message.emit("相同規格的任務已在佇列中")
                return
            task = {"id": uuid.uuid4().hex, "url": self._url, "video_id": self._media["id"], "title": self._media["title"],
                    "thumbnail": self._media["thumbnail"], "folder": str(folder), "options": options, "plan": p,
                    "state": "queued", "detail": p["summary"], "progress": -1, "speed": "", "eta": "", "path": "", "error": "", "created": time.time(), "attempt": 0}
            self.model.add(task)
            self.persist()
            self.changed.emit()
            self.schedule()
        except (OSError, UserError) as exc:
            self.message.emit(str(exc))

    def schedule(self):
        if self.closing or self._update_busy: return
        for task in reversed(self.model.items):
            if len(self.runners) >= self._settings["concurrency"]: break
            if task["state"] != "queued" or task["id"] in self.runners: continue
            runner = Download(task, self)
            self.runners[task["id"]] = runner
            runner.changed.connect(lambda t=task: self.task_changed(t))
            runner.finished.connect(lambda t=task, r=runner: self.task_finished(t, r))
            QTimer.singleShot(0, runner.start)

    def acquire_conversion(self, runner, callback):
        if self.processing_owner is None:
            self.processing_owner = runner
            runner.conversion_owned = True
            QTimer.singleShot(0, lambda: callback() if not runner.cancelled else None)
        else:
            runner.status("waiting_processing", "等候其他轉換完成，避免過度占用 CPU")
            self.processing_waiters.append((runner, callback))

    def release_conversion(self, runner):
        self.processing_waiters = [(r, cb) for r, cb in self.processing_waiters if r is not runner]
        if self.processing_owner is runner:
            self.processing_owner = None
            if self.processing_waiters:
                following, callback = self.processing_waiters.pop(0)
                self.acquire_conversion(following, callback)

    def task_changed(self, task):
        self.model.refresh(task)
        self.save_timer.start()
        self.changed.emit()

    def task_finished(self, task, runner):
        self.runners.pop(task["id"], None)
        self.release_conversion(runner)
        runner.deleteLater()
        if task["state"] == "failed" and task.get("retryable") and task.get("attempt", 0) < 1 and not self.closing:
            task["attempt"] = task.get("attempt", 0) + 1
            task.update(state="queued", detail="暫時性連線失敗，等待 4 秒後重試")
            # Reserve queue delay explicitly, including across other completions.
            task["state"] = "recoverable"
            QTimer.singleShot(4000, lambda t=task: self._auto_retry(t))
        elif task["state"] == "completed":
            self.message.emit("下載完成：" + task["title"])
            if self._settings["notifications"] and QSystemTrayIcon.supportsMessages():
                self.tray.show()
                self.tray.showMessage("下載完成", task["title"], QSystemTrayIcon.MessageIcon.Information, 5000)
                QTimer.singleShot(7000, self.tray.hide)
        self.task_changed(task)
        self.persist()
        if self.closing:
            self._maybe_finish_shutdown()
        else: self.schedule()

    def _auto_retry(self, task):
        if task["state"] == "recoverable" and not self.closing:
            task.update(state="queued", detail="正在重試")
            self.task_changed(task)
            self.schedule()

    @Slot(str)
    def cancel(self, task_id):
        task = next((t for t in self.model.items if t["id"] == task_id), None)
        if not task: return
        if task_id in self.runners: self.runners[task_id].cancel()
        elif task["state"] in ("queued", "recoverable"):
            task.update(state="cancelled", detail="已取消，可重試", progress=-1)
            self.task_changed(task)
            self.persist()

    @Slot(str)
    def retry(self, task_id):
        task = next((t for t in self.model.items if t["id"] == task_id), None)
        if task and task["state"] in ("failed", "cancelled", "recoverable"):
            task.update(state="queued", detail="等待重新確認來源", error="", attempt=0, retryable=False)
            self.task_changed(task)
            self.persist()
            self.schedule()

    @Slot(str)
    def saveElsewhere(self,task_id):
        task = next((t for t in self.model.items if t["id"]==task_id),None)
        if not task or task["state"] not in ("failed","cancelled","recoverable"): return
        folder = QFileDialog.getExistingDirectory(None,"選擇此任務的新儲存位置",self._settings["folder"])
        if folder:
            task["folder"]=folder
            self.retry(task_id)

    @Slot(str)
    def remove(self, task_id):
        for i, task in enumerate(self.model.items):
            if task["id"] == task_id and task["state"] not in ACTIVE:
                self.model.beginRemoveRows(QModelIndex(), i, i)
                self.model.items.pop(i)
                self.model.endRemoveRows()
                self.persist()
                self.changed.emit()
                break

    @Slot(str)
    def copyDiagnostic(self, task_id):
        task = next((t for t in self.model.items if t["id"] == task_id), None)
        detail = redact(task.get("diagnostic") or task.get("error", "")) if task else getattr(self, "last_diagnostic", self._error)
        QGuiApplication.clipboard().setText("Video Downloader " + VERSION + "\n" + json.dumps(self._versions) + "\n" + detail)
        self.message.emit("已複製診斷資訊，來源網址與使用者目錄已隱藏")

    @Slot(str)
    def openFile(self, task_id):
        task = next((t for t in self.model.items if t["id"] == task_id), None)
        if task and task["state"] == "completed" and Path(task.get("path", "")).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(task["path"]))
        else: self.message.emit("找不到檔案，可能已被移動或刪除")

    @Slot(str)
    def openFolder(self, task_id):
        task = next((t for t in self.model.items if t["id"] == task_id), None)
        folder = task["folder"] if task else self._settings["folder"]
        if Path(folder).is_dir(): QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else: self.message.emit("儲存資料夾目前無法使用")

    def persist(self):
        try:
            tasks = [t | {"diagnostic": redact(t.get("diagnostic", ""))} for t in self.model.items]
            atomic_json(DATA / "tasks.json", tasks)
        except OSError:
            self.message.emit("無法保存任務資料；請確認本機資料夾空間與權限")

    def check_dependencies(self):
        for name in self._versions:
            args = ["-version"] if name.startswith("ff") else ["--version"]
            process = ManagedProcess(tool(name), args, self, timeout=20000)
            self.checkers.append(process)
            def done(code, output, n=name, p=process):
                self._dependency_ok[n] = code == 0 and bool(output.strip())
                self._versions[n] = output.strip().splitlines()[0][:110] if code == 0 and output.strip() else "無法使用；請重新安裝或回復核心"
                self.checkers.remove(p)
                p.deleteLater()
                self.changed.emit()
                if n=="yt-dlp" and code and read_json(DATA/"core-active.json",{}) and not self._fallback_attempted:
                    self._fallback_attempted=True
                    try:
                        atomic_json(DATA/"core-active.json",{})
                        self.message.emit("更新核心無法啟動，已回復隨附版本")
                        QTimer.singleShot(0,self.check_dependencies)
                    except OSError:
                        self.message.emit("核心無法啟動且無法保存回復設定，請重新安裝")
            process.done.connect(done)
            process.start()

    @Slot()
    def checkUpdate(self): self._start_update(False)
    @Slot()
    def installUpdate(self):
        if self.activeCount or self._busy:
            self.message.emit("請等所有下載及解析結束後，再更新核心")
            return
        self._start_update(True)

    def _start_update(self, install):
        if self.app_updates.installPending:
            self.message.emit("請先完成或取消 App 更新")
            return
        if self._update_busy: return
        self._update_busy = True
        self._update_message = "正在下載、驗證並測試新核心…" if install else "正在查詢官方版本…"
        self.changed.emit()
        worker = UpdateWorker(install, self._latest, self)
        self.update_worker = worker
        def result(ok, version, text):
            self._update_message = text
            if ok: self._latest = version
            if ok and install: self.check_dependencies()
            self.changed.emit()
        def finished():
            self._update_busy = False
            self.update_worker = None
            worker.deleteLater()
            self.changed.emit()
            self.schedule()
        worker.result.connect(result)
        worker.finished.connect(finished)
        worker.start()

    @Slot()
    def rollbackCore(self):
        if self.activeCount or self._busy or self._update_busy or self.app_updates.installPending:
            self.message.emit("請等執行中的工作結束後再回復核心")
            return
        try:
            atomic_json(DATA / "core-active.json", {})
            self.check_dependencies()
            self.message.emit("已回復隨附的下載核心")
        except OSError: self.message.emit("核心設定無法寫入")

    @Slot()
    def cleanTemp(self,quiet=False):
        # Explicit user action; only expired, marked workspaces in known task folders.
        removed = 0
        registry=read_json(DATA/"workspaces.json",[])
        registry=registry if isinstance(registry,list) else []
        retained=[]
        for location in registry:
            child=Path(location)
            if child.is_symlink() or child.parent.name!=".video-downloader" or not re.fullmatch(r"[a-f0-9]{32}",child.name):
                continue
            if not child.is_dir(): continue
            marker=read_json(child/".owner.json",{})
            try: created=float(marker.get("created",time.time())) if isinstance(marker,dict) else time.time()
            except (ValueError,TypeError): created=time.time()
            if (isinstance(marker,dict) and marker.get("app")=="VideoDownloader" and marker.get("task")==child.name
                and child.name not in self.runners and time.time()-created>7*86400):
                try:
                    shutil.rmtree(child)
                    removed+=1
                    continue
                except OSError:
                    self.message.emit("部分暫存無法清理，可能被占用或沒有權限")
            retained.append(location)
        try: atomic_json(DATA/"workspaces.json",retained)
        except OSError: self.message.emit("無法保存暫存清理紀錄")
        if not quiet:
            self.message.emit(f"已清理 {removed} 個超過 7 天的暫存工作區")

    @Slot(result=bool)
    def requestClose(self):
        return self.activeCount == 0 and not self._busy and not self._update_busy and not self.app_updates.busy and not self.app_updates.installPending

    def _try_app_install(self):
        if (not self.closing and self.app_updates.state == "ready" and self.app_updates.installPending
                and not self.app_updates.busy and not self.activeCount and not self._busy
                and not self._update_busy and not self.checkers):
            self.persist()
            self.app_updates.launch_install()

    def _quit_for_update(self):
        self.closing = True
        self.persist()
        self.app_update_timer.stop()
        self.shutdownReady.emit()

    def _maybe_finish_shutdown(self):
        if self.closing and not self.runners and not self.app_updates.busy and not self._update_busy:
            self.shutdownReady.emit()

    @Slot()
    def shutdown(self):
        if self._update_busy:
            self.message.emit("更新正在處理中，請等待完成後再結束")
            return
        self.closing = True
        self.app_update_timer.stop()
        self.app_updates.cancel()
        self.cancelParse()
        for task in self.model.items:
            if task["state"] == "queued": task.update(state="recoverable", detail="結束時尚未開始")
        for runner in list(self.runners.values()): runner.cancel()
        self.persist()
        self._maybe_finish_shutdown()
