"""Real network download of explicitly Creative-Commons-licensed Blender film.

Not a generic network unit test. Produces a machine-readable evidence report.
"""
import json
from pathlib import Path
import sys
import time
import uuid
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QTimer
from app.formats import normalize, plan, codec_name
from app.engine import Download, core_args
from app.storage import tool

ROOT = Path(__file__).resolve().parents[1]
app = QCoreApplication([])
metadata = subprocess.run([tool("yt-dlp"),*core_args(),"--skip-download","--dump-single-json","--","https://www.youtube.com/watch?v=aqz-KE-bpKQ"],capture_output=True,timeout=180,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
if metadata.returncode: raise SystemExit(metadata.stderr.decode("utf-8",errors="replace"))
media = normalize(json.loads(next(line for line in reversed(metadata.stdout.decode("utf-8").splitlines()) if line.startswith("{"))))
assert "Creative Commons" in media["license"], "Explicit license required for network integration fixture"
mode = sys.argv[1] if len(sys.argv) > 1 else "video"
vi = next(i for i,f in enumerate(media["videos"]) if f["height"] <= 360 and codec_name(f["vcodec"]) == "H.264")
ai = next(i for i,f in enumerate(media["audios"]) if codec_name(f["acodec"]) == "AAC" and 100 < f["abr"] < 200)
p = plan(media, mode, vi, "mp4", "mp3" if mode == "audio" else "original", "192", ai)
folder = ROOT / "evidence" / "downloads"
folder.mkdir(parents=True, exist_ok=True)
task = {"id": uuid.uuid4().hex, "url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ", "video_id": media["id"],
        "title": media["title"], "folder": str(folder), "options": {"mode": mode, "container": "mp4", "audio_format": "mp3" if mode == "audio" else "original", "bitrate": "192",
        "video_id": media["videos"][vi]["id"] if mode == "video" else "", "audio_id": media["audios"][ai]["id"]}, "plan": p}
runner = Download(task)
last = [None]
start = time.monotonic()
def changed():
    if task["state"] != last[0]:
        print(task["state"], task["detail"], flush=True)
        last[0] = task["state"]
def done():
    report = {"time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": time.monotonic()-start,
              "source_license": media["license"], "source": task["url"], "plan": p, "task": task}
    (ROOT / "evidence" / ("integration-" + mode + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT", task["state"], task.get("error", ""), task.get("path", ""), flush=True)
    app.exit(0 if task["state"] == "completed" else 1)
runner.changed.connect(changed)
runner.finished.connect(done)
QTimer.singleShot(0, runner.start)
QTimer.singleShot(600000, runner.cancel)
sys.exit(app.exec())
