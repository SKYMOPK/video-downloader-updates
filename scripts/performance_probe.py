"""Short targeted idle probe: count actual rendered frames, not host CPU load."""
import json
import os
from pathlib import Path
import sys
import time
import psutil
ROOT=Path(__file__).resolve().parents[1]
os.environ["VD_DATA_DIR"]=str(ROOT/"work-performance-data")
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer,QUrl,QObject
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from app.controller import Controller
app=QApplication([])
QQuickStyle.setStyle("Basic")
backend=Controller(app)
engine=QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend",backend)
engine.load(QUrl.fromLocalFile(str(ROOT/"qml/Main.qml")))
window=engine.rootObjects()[0]
frames=[0]
window.frameSwapped.connect(lambda:frames.__setitem__(0,frames[0]+1))
process=psutil.Process()
report=[]
baseline=[None]
def mark():
    baseline[0]=(time.perf_counter(),process.cpu_times(),frames[0])
def measure(label):
    now=time.perf_counter();cpu=process.cpu_times();start,prior,count=baseline[0]
    report.append({"label":label,"seconds":now-start,"frames":frames[0]-count,"single_core_cpu_percent":((cpu.user+cpu.system)-(prior.user+prior.system))/(now-start)*100,"rss_mib":process.memory_info().rss/1024**2})
    mark()
def change_focus():
    measure("initial-idle")
    field=window.findChild(QObject,"urlField")
    if field:field.setProperty("focus",False)
    mark()
def finish():
    measure("without-text-caret")
    (ROOT/"evidence/performance-probe.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    backend.shutdown()
    app.quit()
QTimer.singleShot(5000,mark)
QTimer.singleShot(20000,change_focus)
QTimer.singleShot(35000,finish)
app.exec()
print(json.dumps(report,indent=2))
