"""Real sidecar tests with self-generated, two-second audiovisual material."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

import psutil
import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtTest import QSignalSpy

from app.engine import Download
from app.process import ManagedProcess
from app.storage import tool, workspace


def wait_for(signal, start, timeout=30000):
    spy = QSignalSpy(signal)
    start()
    if not spy.count(): spy.wait(timeout)
    assert spy.count(), "asynchronous operation timed out"
    return spy.at(0)


@pytest.mark.parametrize("mode,ext,transcode", [("video","mp4",False),("video","mkv",False),("video","mp4",True),
    ("audio","m4a",False),("audio","mp3",True),("audio","opus",True),("audio","wav",True)])
def test_real_processing_and_validation(qt, tmp_path, mode, ext, transcode):
    task = {"id": uuid.uuid4().hex, "folder": str(tmp_path), "title": "影音測試 Unicode", "video_id": "fixture", "seconds": 2,
            "plan": {"mode":mode,"ext":ext,"transcode":transcode,"height":144,"fps":30,"bitrate":192}}
    runner = Download(task, qt)
    runner.work = workspace(tmp_path, task["id"])
    runner.source = runner.work / "source.mkv"
    result = subprocess.run([tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=256x144:rate=30:duration=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(runner.source)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    runner.plan = task["plan"]
    wait_for(runner.finished, lambda: runner._downloaded(0, ""))
    assert task["state"] == "completed", task
    path = Path(task["path"])
    assert path.exists() and path.suffix == "." + ext
    decoded = subprocess.run([tool("ffmpeg"), "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True)
    assert decoded.returncode == 0, decoded.stderr.decode(errors="replace")


def test_invalid_output_never_completes(qt, tmp_path):
    task = {"id": "fixture", "title": "bad", "video_id":"x", "folder":str(tmp_path)}
    runner = Download(task)
    runner.plan = {"mode":"video", "height":144}
    runner.target = tmp_path / "bad.mp4"
    runner.target.write_bytes(b"broken")
    runner._verified(1, "invalid data")
    assert task["state"] == "failed" and not task.get("path")


def test_cancel_kills_descendant_process(qt, tmp_path):
    pidfile = tmp_path / "child.pid"
    child_code = "import time; time.sleep(90)"
    parent_code = "import subprocess,sys,pathlib,time; p=subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid)); print('READY',flush=True); time.sleep(90)"
    process = ManagedProcess(sys.executable, ["-c", parent_code], timeout=15000)
    process.line.connect(lambda text: QTimer.singleShot(100, process.cancel) if text == "READY" else None)
    code, output = wait_for(process.done, process.start)
    assert pidfile.exists(), output
    pid = int(pidfile.read_text())
    # Kernel job termination can take a short time to reap process handles.
    deadline = time.monotonic() + 2
    while psutil.pid_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)
    assert code != 0


def test_retained_output_can_be_saved_elsewhere_without_network(qt,tmp_path,monkeypatch):
    old,new=tmp_path/"old",tmp_path/"new"
    old.mkdir();new.mkdir()
    identifier=uuid.uuid4().hex
    work=workspace(old,identifier)
    retained=work/"output.mp3"
    subprocess.run([tool("ffmpeg"),"-v","error","-f","lavfi","-i","sine=duration=2","-c:a","libmp3lame",str(retained)],check=True,capture_output=True)
    task={"id":identifier,"folder":str(new),"title":"保留成果","video_id":"fixture","seconds":2,
          "ready_output":True,"retained_output":str(retained),"plan":{"mode":"audio","ext":"mp3","transcode":True,"bitrate":192}}
    runner=Download(task,qt)
    monkeypatch.setattr(runner,"_parsed",lambda *a:pytest.fail("Retained output must not re-download"))
    wait_for(runner.finished,runner.start)
    assert task["state"]=="completed",task
    assert Path(task["path"]).parent==new
    assert retained.exists()


@pytest.mark.parametrize("change",["height","fps","container"])
def test_wrong_output_spec_never_completes(qt,tmp_path,change):
    task={"id":uuid.uuid4().hex,"folder":str(tmp_path),"title":"wrong","video_id":"x","seconds":2}
    runner=Download(task,qt)
    runner.plan={"mode":"video","ext":"mp4","height":144,"fps":30,"transcode":False}
    runner.target=tmp_path/"output.mp4"
    runner.target.write_bytes(b"placeholder for pure validation test")
    probe={"streams":[{"codec_type":"video","height":144,"avg_frame_rate":"30/1"},{"codec_type":"audio","codec_name":"aac"}],"format":{"duration":"2","format_name":"mov,mp4"}}
    if change=="height":probe["streams"][0]["height"]=720
    elif change=="fps":probe["streams"][0]["avg_frame_rate"]="60/1"
    else:probe["format"]["format_name"]="matroska"
    runner._verified(0,json.dumps(probe))
    assert task["state"]=="failed" and not task.get("path")
