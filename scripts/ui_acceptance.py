"""Real backend + real QML acceptance harness. Uses isolated app data and outputs.

No fabricated network/format/progress data. Qt component calls are test harness
operations; native Windows click/keyboard checks are recorded separately.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.environ["VD_DATA_DIR"] = str(ROOT / "work-ui-data")
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer,QUrl,QObject,QMetaObject,Qt,qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from app.controller import Controller
from app.formats import codec_name

app=QApplication([])
app.setFont(QFont("Microsoft JhengHei UI",10))
QQuickStyle.setStyle("Basic")
warnings=[]
qInstallMessageHandler(lambda kind,context,message:warnings.append(str(message)))
backend=Controller(app)
backend._settings.update(folder=str(ROOT/"evidence/ui-downloads"),notifications=False,concurrency=1)
Path(backend.settings["folder"]).mkdir(parents=True,exist_ok=True)
backend.model.beginResetModel()
backend.model.items=[]
backend.model.endResetModel()
engine=QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend",backend)
engine.load(QUrl.fromLocalFile(str(ROOT/"qml/Main.qml")))
assert engine.rootObjects(),warnings
window=engine.rootObjects()[0]
states=set()
report={"real_network":True,"dpr":window.devicePixelRatio(),"screenshots":[],"warnings":warnings}
start=time.monotonic()
phase=[0]

def snapshot(name):
    path=ROOT/"evidence"/("ui-"+name+".png")
    window.grabWindow().save(str(path))
    report["screenshots"].append(path.name)

def tick():
    if phase[0]==0 and backend.media and backend.canDownload:
        phase[0]=1
        snapshot("parsed-video")
        backend.select("mode","audio")
        QTimer.singleShot(300,lambda:snapshot("audio-mode"))
        QTimer.singleShot(500,settings)
    for task in backend.model.items:
        state=task["state"]
        if state not in states:
            states.add(state)
            QTimer.singleShot(70,lambda s=state:snapshot(s))
    if phase[0]==3 and backend.taskCount>=3 and not backend.activeCount:
        phase[0]=4
        snapshot("tasks-finished")
        report["tasks"]=[{k:t.get(k) for k in ("state","title","path","error","plan")} for t in backend.model.items]
        window.setWidth(900);window.setHeight(640)
        QTimer.singleShot(300,lambda:snapshot("small-window"))
        QTimer.singleShot(500,lambda:backend.parse("https://invalid.example/watch"))
        QTimer.singleShot(900,finish)
    if time.monotonic()-start>400:
        report["timeout"]=True
        finish()

def settings():
    dialog=window.findChild(QObject,"settingsDialog")
    assert dialog
    QMetaObject.invokeMethod(dialog,"open")
    QTimer.singleShot(300,lambda:snapshot("settings"))
    QTimer.singleShot(500,lambda:QMetaObject.invokeMethod(dialog,"close"))
    QTimer.singleShot(800,enqueue)

def enqueue():
    backend.select("mode","video")
    vi=next(i for i,f in enumerate(backend.media["videos"]) if f["height"]<=360 and codec_name(f["vcodec"])=="H.264")
    ai=next(i for i,f in enumerate(backend.media["audios"]) if codec_name(f["acodec"])=="AAC" and 100<f["abr"]<200)
    backend.select("video_index",str(vi));backend.select("audio_index",str(ai))
    backend.enqueue()
    backend.select("mode","audio");backend.select("audio_format","mp3")
    backend.enqueue()
    backend.select("audio_format","wav")
    backend.enqueue()
    backend.cancel(backend.model.items[0]["id"])
    phase[0]=3

def finish():
    timer.stop()
    snapshot("invalid-url")
    report["duration_seconds"]=round(time.monotonic()-start,2)
    report["states"]=sorted(states)
    report["warnings"]=warnings
    (ROOT/"evidence/ui-acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    backend.shutdown()
    app.quit()

timer=QTimer()
timer.setInterval(150)
timer.timeout.connect(tick)
timer.start()
QTimer.singleShot(300,lambda:backend.parse("https://www.youtube.com/watch?v=aqz-KE-bpKQ"))
app.exec()
print(json.dumps(report,ensure_ascii=False,indent=2))
