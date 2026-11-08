"""Isolated UI acceptance using an explicitly labelled future-version fixture."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VD_DATA_DIR"] = str(ROOT / "work-app-update-ui")
os.environ["VD_DISABLE_APP_UPDATE_CHECK"] = "1"
from PySide6.QtCore import QObject, QMetaObject, QUrl, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from app.controller import Controller
from app.update_protocol import parse_release
from app.release import REPOSITORY

app = QApplication([])
QQuickStyle.setStyle("Basic")
warnings = []
qInstallMessageHandler(lambda kind, context, text: warnings.append(str(text)))
backend = Controller()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend", backend)
engine.load(QUrl.fromLocalFile(str(ROOT / "qml/Main.qml")))
assert engine.rootObjects(), warnings
window = engine.rootObjects()[0]
updates = backend.app_updates
future = "0.2.1"
name = f"VideoDownloader-{future}-win64-update.zip"
fixture = {"tag_name": "v" + future, "body": "更新介面驗收測試（未發布版本）\n\n改善介面與穩定性，保留目前設定和下載紀錄。", "assets": [
    {"name": name, "size": 183_000_000, "digest": "sha256:" + "0" * 64,
     "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/v{future}/{name}"}]}
updates.release = parse_release(fixture, REPOSITORY, updates.currentVersion)
updates._state, updates._message = "available", "發現新的 App 版本"
updates.changed.emit()
QTest.qWait(300)
assert window.findChild(QObject, "appUpdateDot").property("visible")
updates.prompt.emit()
QTest.qWait(300)
dialog = window.findChild(QObject, "appUpdateDialog")
assert dialog.property("visible")
assert window.grabWindow().save(str(ROOT / "evidence/app-update-dialog.png"))
QMetaObject.invokeMethod(dialog, "close")
settings = window.findChild(QObject, "settingsDialog")
QMetaObject.invokeMethod(settings, "open")
QTest.qWait(300)
assert window.grabWindow().save(str(ROOT / "evidence/app-update-settings.png"))
QMetaObject.invokeMethod(settings, "close")
updates.setShowPrompts(False)
assert updates.available and not updates.showPrompts
assert not warnings, warnings
(ROOT / "evidence/app-update-ui.json").write_text(json.dumps({"fixture": True, "red_dot": True, "dialog": True, "settings": True, "warnings": warnings}, indent=2))
window.setProperty("allowClose", True)
window.close()
backend.closing = True
print("App update dialog, red dot and settings UI passed; no QML warnings.")
