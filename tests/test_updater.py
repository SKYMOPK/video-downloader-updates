import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.updater as module
from app.storage import atomic_json, read_json


@pytest.fixture
def release(tmp_path,monkeypatch):
    monkeypatch.setattr(module,"DATA",tmp_path)
    version="2026.10.26"
    payload=b"verified executable test fixture"
    digest=hashlib.sha256(payload).hexdigest()
    url=f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/yt-dlp.exe"
    meta={"tag_name":version,"assets":[{"name":"yt-dlp.exe","browser_download_url":url,"digest":"sha256:"+digest}]}
    def fake_get(value,limit=2_000_000):
        if value.endswith("/latest"):return json.dumps(meta).encode()
        if value.endswith("SHA2-256SUMS"):return (digest+"  yt-dlp.exe\n").encode()
        return payload
    monkeypatch.setattr(module,"get",fake_get)
    monkeypatch.setattr(module.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0,stdout=version.encode()))
    return tmp_path,meta,payload


def test_update_activation_is_after_validation(release):
    root,meta,payload=release
    atomic_json(root/"core-active.json",{"version":"2026.09.01"})
    worker=module.UpdateWorker(True,meta["tag_name"])
    results=[]
    worker.result.connect(lambda *a:results.append(a))
    worker.run()
    assert results[0][0]
    assert read_json(root/"core-active.json",{})["version"]==meta["tag_name"]
    assert read_json(root/"core-previous.json",{})["version"]=="2026.09.01"


def test_changed_release_requires_new_confirmation(release):
    root,meta,payload=release
    atomic_json(root/"core-active.json",{"version":"2026.09.01"})
    worker=module.UpdateWorker(True,"2026.09.20")
    results=[]
    worker.result.connect(lambda *a:results.append(a))
    worker.run()
    assert not results[0][0]
    assert read_json(root/"core-active.json",{})["version"]=="2026.09.01"


def test_hash_failure_does_not_switch(release):
    root,meta,payload=release
    meta["assets"][0]["digest"]="sha256:"+"0"*64
    worker=module.UpdateWorker(True,meta["tag_name"])
    results=[]
    worker.result.connect(lambda *a:results.append(a))
    worker.run()
    assert not results[0][0] and not (root/"core-active.json").exists()


def test_failed_launch_leaves_active_core_untouched(release,monkeypatch):
    root,meta,payload=release
    atomic_json(root/"core-active.json",{"version":"2026.09.01"})
    monkeypatch.setattr(module.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=1,stdout=b""))
    worker=module.UpdateWorker(True,meta["tag_name"])
    worker.run()
    assert read_json(root/"core-active.json",{})["version"]=="2026.09.01"
    assert not (root/"cores"/(meta["tag_name"]+".staging")).exists()


def test_corrupted_existing_version_is_not_activated(release):
    root,meta,payload=release
    version=root/"cores"/meta["tag_name"]
    version.mkdir(parents=True)
    (version/"yt-dlp.exe").write_bytes(b"corrupted")
    worker=module.UpdateWorker(True,meta["tag_name"])
    results=[]
    worker.result.connect(lambda *a:results.append(a))
    worker.run()
    assert not results[0][0] and not (root/"core-active.json").exists()
