import copy
import json
import time
from PySide6.QtCore import QObject, QEventLoop, QTimer, Signal
import pytest

import app.storage as storage
import app.controller as module
from app.storage import atomic_json


@pytest.fixture
def controller(qt, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA", tmp_path)
    monkeypatch.setattr(module, "DATA", tmp_path)
    monkeypatch.setattr(module.Controller, "check_dependencies", lambda self: None)
    ctl = module.Controller(qt)
    yield ctl
    ctl.save_timer.stop()
    ctl.closing = True
    ctl.deleteLater()


def task(identifier, state="queued"):
    return {"id":identifier,"url":"https://www.youtube.com/watch?v=aqz-KE-bpKQ","title":"測試","state":state,
            "folder":"C:/test","options":{},"plan":{},"detail":"","progress":-1}


def test_restore_unfinished_and_preserve_completed(qt,tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"DATA",tmp_path)
    monkeypatch.setattr(module,"DATA",tmp_path)
    monkeypatch.setattr(module.Controller,"check_dependencies",lambda self:None)
    atomic_json(tmp_path/"tasks.json",[task("unfinished","downloading"),task("done","completed")])
    ctl=module.Controller(qt)
    assert ctl.model.items[0]["state"]=="recoverable"
    assert ctl.model.items[1]["state"]=="completed"
    assert ctl.activeCount==0
    ctl.deleteLater()


def test_queued_cancellation_is_terminal(controller):
    t=task("queued")
    controller.model.add(t)
    controller.cancel("queued")
    controller._auto_retry(t)
    assert t["state"]=="cancelled" and controller.activeCount==0


def test_save_settings_validation(controller):
    controller.setSetting("concurrency",99)
    assert controller.settings["concurrency"]==3
    controller.setSetting("mode","invalid")
    assert controller.settings["mode"]=="video"
    assert storage.load_settings()["concurrency"]==3


def test_startup_blocks_download_until_dependency_checks(controller):
    assert not controller.canDownload
    assert not controller.requestClose() if controller._update_busy else controller.requestClose()


def test_no_schedule_during_update(controller):
    controller.model.add(task("wait"))
    controller._update_busy=True
    controller.schedule()
    assert not controller.runners


def test_terminal_tasks_cannot_be_cancelled(controller):
    t=task("done","completed")
    controller.model.add(t)
    controller.cancel("done")
    assert t["state"]=="completed"


def test_diagnostic_redacts_private_locations_and_query():
    from pathlib import Path
    result=module.redact(str(Path.home())+'/file https://server/video?token=secret&x=1')
    assert "secret" not in result and str(Path.home()) not in result


def test_serial_conversion_gate(controller,qt):
    class Fake(QObject):
        cancelled=False
        conversion_owned=False
        def status(self,*args): self.state=args[0]
    first,second=Fake(controller),Fake(controller)
    called=[]
    controller.acquire_conversion(first,lambda:called.append("first"))
    controller.acquire_conversion(second,lambda:called.append("second"))
    assert first.conversion_owned and not second.conversion_owned
    assert second.state=="waiting_processing"
    controller.release_conversion(first)
    assert second.conversion_owned
    qt.processEvents()
    assert called==["first","second"]


def test_remove_task_does_not_remove_download(controller,tmp_path):
    output=tmp_path/"keep.mp4"
    output.write_bytes(b"user result")
    t=task("done","completed")|{"path":str(output)}
    controller.model.add(t)
    controller.remove("done")
    assert output.read_bytes()==b"user result" and controller.taskCount==0


def test_invalid_new_input_clears_old_result(controller):
    controller._media={"title":"old source"}
    controller._url="https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    controller.parse("https://invalid.example/")
    assert not controller.media and not controller.canDownload and controller.error


def test_editing_url_invalidates_result_before_debounce(controller):
    controller._media={"title":"old source"}
    controller._url="https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    controller.inputEdited("https://youtu.be/differentxx")
    assert not controller.media and not controller.canDownload


def test_quality_selection_tracks_container_without_changing_resolution(controller):
    controller._media = {"videos": [
        {"height": 1080, "fps": 60, "vcodec": "vp9", "tbr": 3000},
        {"height": 1080, "fps": 60, "vcodec": "avc1", "tbr": 2000},
        {"height": 480, "fps": 30, "vcodec": "avc1", "tbr": 600}]}
    controller.select("quality_index", "0")
    assert controller.videoIndex == 1 and controller.qualityIndex == 0
    controller.select("container", "webm")
    assert controller.videoIndex == 0 and controller.qualityIndex == 0
    controller.select("quality_index", "1")
    assert controller.videoIndex == 2 and controller.qualityIndex == 1
    controller.select("quality_index", "99")
    assert controller.videoIndex == 2


def test_app_update_waits_for_downloads_parse_and_core_work(controller, monkeypatch):
    updates = controller.app_updates
    updates._state, updates._pending = "ready", True
    calls = []
    monkeypatch.setattr(updates, "launch_install", lambda: calls.append(True))
    pending = task("existing")
    controller.model.add(pending)
    controller._try_app_install()
    assert not calls
    pending["state"] = "completed"
    controller._busy = True
    controller._try_app_install()
    assert not calls
    controller._busy, controller._update_busy = False, True
    controller._try_app_install()
    assert not calls
    controller._update_busy = False
    controller._try_app_install()
    assert calls == [True]


def test_app_update_prevents_new_work_and_core_check_during_handoff(controller):
    controller.app_updates._pending = True
    controller.parse("https://youtu.be/aqz-KE-bpKQ")
    controller.checkUpdate()
    assert not controller.parser and not controller.update_worker
    assert not controller.canDownload


def test_expired_cleanup_only_removes_owned_workspaces(controller,tmp_path):
    import uuid
    identifier=uuid.uuid4().hex
    work=storage.workspace(tmp_path/"downloads",identifier)
    marker=storage.read_json(work/".owner.json",{})
    marker["created"]=time.time()-8*86400
    atomic_json(work/".owner.json",marker)
    unrelated=tmp_path/"user-files"
    unrelated.mkdir()
    (unrelated/"keep.txt").write_text("keep")
    registry=storage.read_json(tmp_path/"workspaces.json",[])
    registry.append(str(unrelated))
    atomic_json(tmp_path/"workspaces.json",registry)
    controller.cleanTemp(True)
    assert not work.exists() and (unrelated/"keep.txt").is_file()
