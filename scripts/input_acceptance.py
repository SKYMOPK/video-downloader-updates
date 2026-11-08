"""Offline keyboard/context-menu regression against the actual QML window."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VD_DATA_DIR"] = str(ROOT / "work-input-data")
from PySide6.QtCore import QObject, QMetaObject, Qt, QUrl, Slot, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from app.controller import Controller
from app.formats import normalize

class Harness(Controller):
    calls = []
    def check_dependencies(self): pass
    @Slot(str)
    def parse(self, value): self.calls.append(value)

app = QApplication([])
QQuickStyle.setStyle("Basic")
warnings = []
qInstallMessageHandler(lambda kind, context, text: warnings.append(str(text)))
backend = Harness()
backend._url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend", backend)
engine.load(QUrl.fromLocalFile(str(ROOT / "qml/Main.qml")))
assert engine.rootObjects(), warnings
window = engine.rootObjects()[0]
field = window.findChild(QObject, "urlField")
window.requestActivate()
QTest.qWait(100)
QMetaObject.invokeMethod(field, "forceActiveFocus")
url = "https://youtu.be/aqz-KE-bpKQ"
app.clipboard().setText(url)
QTest.keyClick(window, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
backend.changed.emit()
QTest.qWait(900)
assert field.property("text") == url, field.property("text")
assert backend.calls == [url], backend.calls
# Typing and backend refreshes must not replace the in-progress text.
QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
for key in (Qt.Key.Key_A, Qt.Key.Key_B, Qt.Key.Key_C):
    QTest.keyClick(window, key)
backend.changed.emit()
assert field.property("text") == "abc"
# Exercise the context-menu action's actual QML paste handler.
QMetaObject.invokeMethod(field, "selectAll")
action = window.findChild(QObject, "pasteUrlAction")
QMetaObject.invokeMethod(action, "triggered")
QTest.qWait(900)
assert field.property("text") == url
assert backend.calls[-1] == url
backend._media = normalize(json.loads((ROOT / "evidence-source.json").read_text(encoding="utf-8")))
backend.changed.emit()
QTest.qWait(200)
combo = window.findChild(QObject, "qualityCombo")
QMetaObject.invokeMethod(combo, "forceActiveFocus")
QTest.keyClick(window, Qt.Key.Key_Space)
QTest.qWait(300)
assert window.grabWindow().save(str(ROOT / "evidence/quality-simplified.png"))
assert any("60 fps" in label for label in backend.videoOptions)
assert not warnings, warnings
report = {"ctrl_v": True, "typing_survives_refresh": True, "context_paste": True,
          "auto_parse": True, "quality_options": backend.videoOptions, "warnings": warnings}
(ROOT / "evidence/input-acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
window.setProperty("allowClose", True)
window.close()
backend.closing = True
