"""Asynchronous download → explicit conversion → probe → atomic publication."""
import json
from pathlib import Path
import shutil
import time
from fractions import Fraction

from PySide6.QtCore import QObject, Signal, QTimer

from .formats import UserError, normalize, plan, classify_error, size_text
from .process import ManagedProcess
from .storage import tool, workspace, publish, read_json


def core_args():
    return ["--ignore-config", "--no-plugin-dirs", "--no-playlist", "--encoding", "utf-8",
            "--js-runtimes", "deno:" + tool("deno"), "--ffmpeg-location", str(Path(tool("ffmpeg")).parent),
            "--socket-timeout", "25", "--retries", "2", "--fragment-retries", "2",
            "--retry-sleep", "http:exp=1:4", "--retry-sleep", "fragment:exp=1:4"]


class Download(QObject):
    changed = Signal()
    finished = Signal()

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task, self.process, self.cancelled = task, None, False
        self.last_progress = 0
        self.downloaded = {}
        self.source = None
        self.work = None
        self.plan = None
        self.conversion_owned = False

    def status(self, state, detail=""):
        self.task.update(state=state, detail=detail, progress=-1, speed="", eta="")
        self.changed.emit()

    def run(self, program, args, callback, timeout=0, line=None):
        process = ManagedProcess(program, args, self, timeout=timeout)
        self.process = process
        if line:
            process.line.connect(line)
        def done(code, output):
            if self.process is process:
                self.process = None
            process.deleteLater()
            if self.cancelled:
                self.status("cancelled", "已停止，暫存保留 7 天，可重試")
                self.finished.emit()
            else:
                callback(code, output)
        process.done.connect(done)
        process.start()

    def start(self):
        if self.cancelled:
            return
        self.task["retryable"] = False
        try:
            folder = Path(self.task["folder"])
            if not folder.is_dir():
                raise UserError("儲存資料夾不存在，請在設定選擇可用位置後重新加入任務")
            self.work = workspace(folder, self.task["id"])
            # Verify write access in this task's own workspace.
            test = self.work / ".write-test"
            test.write_text("ok")
            test.unlink()
            # A previous run may have completed processing but failed publishing.
            saved = Path(self.task.get("retained_output") or self.work / ("output." + self.task["plan"]["ext"]))
            marker = saved.parent / ".owner.json"
            owner = read_json(marker,{})
            if self.task.get("ready_output") and saved.is_file() and isinstance(owner,dict) and owner.get("app")=="VideoDownloader" and owner.get("task")==self.task["id"] and saved.parent.name == self.task["id"]:
                self.plan = self.task["plan"]
                self.target = self.work / ("output." + self.plan["ext"])
                if saved.resolve() == self.target.resolve():
                    self.status("verifying", "正在重新驗證保留的處理成果")
                    self.run(tool("ffprobe"), ["-v", "error", "-show_format", "-show_streams", "-of", "json", str(saved)], self._verified, 60000)
                else:
                    self.status("merging", "正在將保留成果重新封裝至新位置，不重新下載")
                    self.run(tool("ffmpeg"), ["-v","error","-nostdin","-y","-i",str(saved),"-map","0","-c","copy",str(self.target)], self._converted)
                return
            self.status("parsing", "正在確認來源與所選規格")
            self.run(tool("yt-dlp"), core_args() + ["--skip-download", "--dump-single-json", "--", self.task["url"]], self._parsed, 180000)
        except (OSError, UserError) as exc:
            self.fail(str(exc))

    def _parsed(self, code, output):
        if code:
            self.fail_output(output)
            return
        try:
            line = next(line for line in reversed(output.splitlines()) if line.startswith("{"))
            media = normalize(json.loads(line))
            options = self.task["options"]
            # Preserve exact stream choice; don't downgrade silently after queueing.
            index = next((i for i, f in enumerate(media["videos"]) if f["id"] == options["video_id"]), -1)
            ai = next((i for i, f in enumerate(media["audios"]) if f["id"] == options["audio_id"]), -1)
            if options["audio_id"] and ai < 0:
                raise UserError("所選音訊或語言已不可用，請重新解析並選擇")
            self.plan = plan(media, options["mode"], index, options["container"], options["audio_format"], options["bitrate"], ai)
            expected = self.task["plan"]
            if self.plan["selector"] != expected["selector"] or self.plan["transcode"] != expected["transcode"]:
                raise UserError("來源規格已改變，請重新解析並確認處理方式")
            self.task["seconds"] = media["seconds"]
            chosen = set(self.plan["selector"].split("+"))
            total = sum(f.get("size", 0) for f in media["videos"] + media["audios"] if f["id"] in chosen)
            if total and shutil.disk_usage(self.work).free < total * 2 + 64 * 1024**2:
                raise UserError("磁碟剩餘空間可能不足以下載與處理此影片，請釋放空間或換位置")
            self.status("downloading", "正在下載來源串流")
            args = core_args() + ["--newline", "--progress", "--no-quiet", "--progress-delta", "0.3", "--no-warnings",
                "--progress-template", "download:VDP:%(progress)j", "--print", "after_move:VDF:%(filepath)j",
                "--no-simulate", "--continue", "--no-overwrites", "--fixup", "never",
                "-f", self.plan["selector"], "--merge-output-format", "mkv", "-o", str(self.work / "source.%(ext)s"), "--", self.task["url"]]
            self.run(tool("yt-dlp"), args, self._downloaded, line=self._line)
        except (ValueError, StopIteration, UserError, KeyError, OSError) as exc:
            self.fail(str(exc) or "無法讀取來源資訊，請重新解析")

    def _line(self, text):
        if text.startswith("VDF:"):
            try:
                self.source = Path(json.loads(text[4:]))
            except ValueError:
                pass
        elif text.startswith("[Merger]"):
            self.status("merging", "正在合併來源影音")
        elif text.startswith("VDP:"):
            try:
                progress = json.loads(text[4:])
                key = str(progress.get("filename") or "stream")
                self.downloaded[key] = progress
                now = time.monotonic()
                if now - self.last_progress < 0.25 and progress.get("status") != "finished":
                    return
                self.last_progress = now
                total = progress.get("total_bytes") or progress.get("total_bytes_estimate") or 0
                downloaded = progress.get("downloaded_bytes") or 0
                percent = min(100, downloaded / total * 100) if total else -1
                # A percentage describes ONLY this stream, never overall completion.
                self.task.update(progress=percent, detail=f"串流 {len(self.downloaded)} · {size_text(downloaded)}" + (f" / 約 {size_text(total)}" if total else ""),
                    speed=(size_text(progress.get("speed")) + "/s") if progress.get("speed") else "",
                    eta=(f"約 {int(progress['eta']) // 60}:{int(progress['eta']) % 60:02}" if progress.get("eta") is not None else ""))
                self.changed.emit()
            except (ValueError, TypeError, KeyError):
                pass

    def _downloaded(self, code, output):
        if code:
            self.fail_output(output)
            return
        if not self.source or not self.source.is_file() or self.source.parent.resolve() != self.work.resolve():
            self.fail("找不到預期下載檔案，已保留暫存資料")
            return
        if self.plan["transcode"] and not self.conversion_owned and hasattr(self.parent(), "acquire_conversion"):
            self.parent().acquire_conversion(self, lambda: self._downloaded(code, output))
            return
        target = self.work / ("output." + self.plan["ext"])
        if target.exists():
            target.unlink()  # Owned, reproducible intermediate only.
        mode, ext, transcode = self.plan["mode"], self.plan["ext"], self.plan["transcode"]
        self.status("converting" if transcode else "merging", "正在轉換音訊／影片" if transcode else "正在保留原始品質並整理輸出")
        args = ["-hide_banner", "-nostdin", "-n", "-i", str(self.source)]
        if mode == "audio":
            args += ["-map", "0:a:0", "-vn"]
            if not transcode:
                args += ["-c:a", "copy"]
            elif ext == "wav":
                args += ["-c:a", "pcm_s16le"]
            else:
                args += ["-c:a", {"mp3": "libmp3lame", "m4a": "aac", "opus": "libopus"}[ext], "-b:a", f"{self.plan['bitrate']}k"]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0"]
            args += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"] if transcode else ["-c", "copy"]
        if ext in ("mp4", "m4a"):
            args += ["-movflags", "+faststart"]
        args += ["-progress", "pipe:1", "-nostats", str(target)]
        self.target = target
        self.run(tool("ffmpeg"), args, self._converted)

    def _converted(self, code, output):
        if code:
            self.fail("影音處理失敗，已保留可恢復的暫存檔", output)
            return
        self.status("verifying", "正在檢查輸出檔案")
        self.run(tool("ffprobe"), ["-v", "error", "-show_format", "-show_streams", "-of", "json", str(self.target)], self._verified, 60000)

    def _verified(self, code, output):
        try:
            if code or not self.target.is_file() or self.target.stat().st_size == 0:
                raise UserError("輸出驗證失敗，檔案不存在或無法讀取")
            probe = json.loads(output)
            streams = probe.get("streams", [])
            audio = [s for s in streams if s.get("codec_type") == "audio"]
            video = [s for s in streams if s.get("codec_type") == "video"]
            if not audio or (self.plan["mode"] == "video" and not video) or (self.plan["mode"] == "audio" and video):
                raise UserError("輸出缺少預期的影音串流，未標記完成")
            if self.plan["mode"] == "video" and int(video[0].get("height", 0)) != self.plan["height"]:
                raise UserError("輸出解析度與指定規格不符，未標記完成")
            if self.plan["mode"] == "video":
                rate = video[0].get("avg_frame_rate") or video[0].get("r_frame_rate")
                try: actual_fps = float(Fraction(rate))
                except (ValueError, ZeroDivisionError, TypeError): actual_fps = 0
                expected_fps = self.plan.get("fps", 0)
                if actual_fps and expected_fps and abs(actual_fps-expected_fps) > max(0.2,expected_fps*0.03):
                    raise UserError("輸出 FPS 與指定規格不符，未標記完成")
                if self.plan["transcode"] and video[0].get("codec_name") != "h264":
                    raise UserError("輸出影片編碼與轉換設定不符")
            container = set(probe.get("format",{}).get("format_name","").split(","))
            expected_containers = {"mp4":{"mov","mp4"}, "m4a":{"mov","m4a","mp4"}, "mkv":{"matroska"},
                                   "webm":{"matroska","webm"}, "mp3":{"mp3"}, "opus":{"ogg"}, "wav":{"wav"}}
            ext = self.plan.get("ext", "")
            if ext in expected_containers and not container.intersection(expected_containers[ext]):
                raise UserError("輸出容器與所選格式不符，未標記完成")
            if self.plan["mode"] == "audio" and self.plan["transcode"]:
                expected_codec = {"mp3":"mp3","m4a":"aac","opus":"opus","wav":"pcm_s16le"}.get(ext)
                if expected_codec and audio[0].get("codec_name") != expected_codec:
                    raise UserError("輸出音訊編碼與轉換設定不符")
            duration = float(probe.get("format", {}).get("duration") or 0)
            expected = self.task.get("seconds", 0)
            if duration <= 0 or (expected and abs(duration - expected) > max(3, expected * 0.02)):
                raise UserError("輸出長度與來源不符，請重試或查看診斷")
            self.task["ready_output"] = True
            self.task["retained_output"] = str(self.target)
            dest = publish(self.target, self.task["folder"], self.task["title"], self.task["video_id"])
            self.task.update(path=dest, progress=100, size=size_text(Path(dest).stat().st_size), completed=time.time(), error="")
            self.status("completed", "已驗證並儲存 · " + self.task["size"])
            self.task["progress"] = 100
            # Only clean our marked workspace after successful publication.
            if self.work and (self.work / ".owner.json").is_file():
                shutil.rmtree(self.work, ignore_errors=True)
            self.finished.emit()
        except (ValueError, OSError, UserError, KeyError, IndexError) as exc:
            self.fail(str(exc) + "；已保留處理成果，可重試儲存", output)

    def fail_output(self, output):
        message, retryable = classify_error(output)
        self.task["retryable"] = retryable
        self.fail(message, output)

    def fail(self, message, diagnostic=""):
        self.task.update(error=message, diagnostic=diagnostic[-12000:])
        self.status("failed", message)
        self.finished.emit()

    def cancel(self):
        self.cancelled = True
        self.status("cancelling", "正在停止相關程序")
        if self.process:
            self.process.cancel()
        else:
            self.status("cancelled", "已停止，可重試")
            self.finished.emit()
