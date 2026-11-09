from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication
import pytest


def qt_message(mode, context, message):
    print("QT", mode, message, flush=True)


qInstallMessageHandler(qt_message)


@pytest.fixture(scope="session")
def qt():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def isolate_persistence(tmp_path,monkeypatch):
    import app.storage as storage
    import app.documents as documents
    import app.document_engine as document_engine
    monkeypatch.setattr(storage,"DATA",tmp_path/"app-data")
    monkeypatch.setattr(documents,"DATA",tmp_path/"app-data")
    monkeypatch.setattr(document_engine,"DATA",tmp_path/"app-data")
    monkeypatch.setenv('VD_DATA_DIR',str(tmp_path/'app-data'))
