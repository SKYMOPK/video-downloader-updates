"""Fast, offline QML rendering at real effective device pixel ratios."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ["VD_DATA_DIR"]=str(ROOT/"work-visual-data"/sys.argv[1])
from PySide6.QtCore import QTimer,QUrl,QObject,QMetaObject,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtQml import QQmlApplicationEngine
from app.controller import Controller

app=QApplication([])
QQuickStyle.setStyle("Basic")
warnings=[]
qInstallMessageHandler(lambda kind,ctx,text:warnings.append(str(text)))
backend=Controller(app)
engine=QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend",backend)
engine.load(QUrl.fromLocalFile(str(ROOT/"qml/Main.qml")))
assert engine.rootObjects(), warnings
window=engine.rootObjects()[0]
if len(sys.argv)>2:
    window.setWidth(900);window.setHeight(640)
def capture():
    label=sys.argv[1]
    window.grabWindow().save(str(ROOT/"evidence"/("dpi-"+label+".png")))
    (ROOT/"evidence"/("dpi-"+label+".json")).write_text(json.dumps({"effective_dpr":window.devicePixelRatio(),"logical_size":[window.width(),window.height()],"warnings":warnings},indent=2))
    backend.shutdown()
    app.quit()
QTimer.singleShot(2000,capture)
app.exec()
