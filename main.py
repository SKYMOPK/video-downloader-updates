import argparse
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile, QTimer, QUrl, QObject, qInstallMessageHandler
from PySide6.QtGui import QFont, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

from app.storage import ROOT, DATA
from app.controller import Controller
from app.release import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="")
    parser.add_argument("--capture", default="")
    parser.add_argument("--quit-after", type=int, default=0)
    parser.add_argument("--update-job", default="")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(DATA / "application.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    qInstallMessageHandler(lambda mode, context, message: logging.warning(message))
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Video Downloader")
    app.setOrganizationName("VideoDownloader")
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "app.ico")))
    app.setFont(QFont("Microsoft JhengHei UI", 10))
    lock = QLockFile(str(DATA / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Video Downloader", "程式已在執行中，請回到已開啟的視窗")
        return 0
    QQuickStyle.setStyle("Basic")
    backend = Controller()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Main.qml")))
    if not engine.rootObjects():
        logging.error("QML could not be loaded")
        return 1
    window = engine.rootObjects()[0]
    if os.name == "nt":
        # Preserve native Windows controls, snap, resize and keyboard behavior.
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(window.winId()), 20, ctypes.byref(enabled), 4)
    backend.shutdownReady.connect(app.quit)
    app.aboutToQuit.connect(backend.persist)
    QTimer.singleShot(2500, backend.app_updates.startup)
    if args.update_job:
        def ready_after_update():
            try:
                from app.update_helper import signal_health
                signal_health(args.update_job, VERSION, sys.executable)
            except Exception:
                logging.error("更新啟動驗證失敗")
                backend.shutdown()
        QTimer.singleShot(1800, ready_after_update)
    if args.url:
        window.findChild(QObject, "urlField").setProperty("text", args.url)
        QTimer.singleShot(300, lambda: backend.parse(args.url))
    if args.capture:
        def capture():
            Path(args.capture).parent.mkdir(parents=True, exist_ok=True)
            window.grabWindow().save(args.capture)
        QTimer.singleShot(5000, capture)
    if args.quit_after:
        QTimer.singleShot(args.quit_after * 1000, backend.shutdown)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    sys.exit(main())
