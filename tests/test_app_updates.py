import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from app import app_updates as module
from app import update_helper as helper
from app.storage import atomic_json, read_json
from app.update_protocol import PRODUCT_ID, extract_package, parse_release, sha256, version_tuple


def release(payload=b"package", version="0.3.0"):
    name = f"VideoDownloader-{version}-win64-update.zip"
    return {"tag_name": "v" + version, "body": "完整 App 更新", "draft": False, "prerelease": False,
            "assets": [{"name": name, "size": len(payload), "state": "uploaded",
                        "browser_download_url": f"https://github.com/{module.REPOSITORY}/releases/download/v{version}/{name}",
                        "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}]}


def create_application(root, version):
    root.mkdir(parents=True)
    (root / "VideoDownloader.exe").write_bytes(b"test exe " + version.encode())
    identity = root / "_internal/app/release.json"
    identity.parent.mkdir(parents=True)
    identity.write_text(json.dumps({"product_id": PRODUCT_ID, "version": version}), encoding="utf-8")
    atomic_json(root / "app-manifest.json", {"product_id": PRODUCT_ID, "version": version,
                "files": {"VideoDownloader.exe": sha256(root / "VideoDownloader.exe"),
                          "_internal/app/release.json": sha256(identity)}})


def archive_application(source, destination, extra=None):
    with zipfile.ZipFile(destination, "w") as archive:
        for path in source.rglob("*"):
            if path.is_file(): archive.write(path, "VideoDownloader/" + path.relative_to(source).as_posix())
        if extra: archive.writestr(*extra)


@pytest.mark.parametrize("value", ["1.0", "1.0.0-beta", "v01.0.0", "../1.0.0", "1.0.0.0"])
def test_version_rejects_unstable_and_ambiguous(value):
    with pytest.raises(ValueError): version_tuple(value)


def test_versions_compare_numerically():
    assert version_tuple("v0.10.0") > version_tuple("0.9.0")
    assert parse_release(release(version="0.2.0"), module.REPOSITORY, "0.2.0") is None


@pytest.mark.parametrize("change", ["draft", "prerelease", "wrong_url", "no_digest", "too_big"])
def test_untrusted_or_incomplete_release_is_rejected(change):
    raw = release()
    if change in ("draft", "prerelease"): raw[change] = True
    if change == "wrong_url": raw["assets"][0]["browser_download_url"] = "https://example.org/update.zip"
    if change == "no_digest": raw["assets"][0].pop("digest")
    if change == "too_big": raw["assets"][0]["size"] = 4 * 1024 ** 3
    with pytest.raises(ValueError): parse_release(raw, module.REPOSITORY, "0.2.0")


@pytest.mark.parametrize("url", ["http://github.com/file", "https://github.com.evil.org/file", "https://user@github.com/file", "https://github.com:444/file"])
def test_redirects_cannot_leave_github_https(url):
    with pytest.raises(ValueError): module.check_url(url)


@pytest.mark.parametrize("path", ["VideoDownloader/../../escape", "VideoDownloader/C:/escape", "VideoDownloader/CON.txt", "VideoDownloader/bad./file", "VideoDownloader/../file"])
def test_archive_rejects_unsafe_paths_before_activation(tmp_path, path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output: output.writestr(path, b"bad")
    with pytest.raises(ValueError): extract_package(archive, tmp_path / "stage", "0.3.0")
    assert not (tmp_path / "escape").exists()


def test_full_package_hash_validation(tmp_path):
    source = tmp_path / "source"
    create_application(source, "0.3.0")
    archive = tmp_path / "update.zip"
    archive_application(source, archive)
    assert extract_package(archive, tmp_path / "stage", "0.3.0")["version"] == "0.3.0"
    (source / "VideoDownloader.exe").write_bytes(b"tampered")
    archive_application(source, archive)
    with pytest.raises(ValueError, match="驗證失敗"):
        extract_package(archive, tmp_path / "tampered", "0.3.0")


@pytest.mark.parametrize("corruption", ["extra_file", "wrong_product", "wrong_version", "duplicate"])
def test_manifest_mismatch_rejected(tmp_path, corruption):
    source = tmp_path / "source"
    create_application(source, "0.3.0")
    if corruption == "wrong_product":
        value = read_json(source / "app-manifest.json", {})
        value["product_id"] = "another app"
        atomic_json(source / "app-manifest.json", value)
    archive = tmp_path / "update.zip"
    extra = ("VideoDownloader/unlisted.txt", b"unknown") if corruption == "extra_file" else (("VideoDownloader/videodownloader.exe", b"duplicate") if corruption == "duplicate" else None)
    archive_application(source, archive, extra)
    with pytest.raises(ValueError):
        extract_package(archive, tmp_path / "stage", "0.4.0" if corruption == "wrong_version" else "0.3.0")


@pytest.mark.parametrize("payload,expected,ok", [(b"package", b"package", True), (b"tampered", b"package", False), (b"short", b"longer-package", False)])
def test_streamed_download_requires_size_and_checksum(qt, tmp_path, monkeypatch, payload, expected, ok):
    monkeypatch.setattr(module, "DATA", tmp_path)
    monkeypatch.setattr(module, "open_url", lambda url: io.BytesIO(payload))
    worker = module.AppUpdateWorker(parse_release(release(expected), module.REPOSITORY, "0.2.0"))
    results = []
    worker.result.connect(lambda *args: results.append(args))
    worker.run()
    assert results[0][0] is ok
    assert len(list(tmp_path.rglob("update.zip"))) == int(ok)
    assert not list(tmp_path.rglob("*.part"))


def test_cancelled_download_never_becomes_installable(qt, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DATA", tmp_path)
    worker = module.AppUpdateWorker(parse_release(release(), module.REPOSITORY, "0.2.0"))
    # run() called directly for deterministic network behavior; interruption is injectable.
    monkeypatch.setattr(worker, "isInterruptionRequested", lambda: True)
    monkeypatch.setattr(module, "open_url", lambda url: io.BytesIO(b"package"))
    results = []
    worker.result.connect(lambda *args: results.append(args))
    worker.run()
    assert not results[0][0] and not list(tmp_path.rglob("update.zip"))


def test_red_dot_and_prompt_persist_without_repeated_dialog(qt, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DATA", tmp_path)
    atomic_json(tmp_path / "app-update-state.json", {"release": release()})
    updates = module.AppUpdates()
    calls = []
    updates.prompt.connect(lambda: calls.append(True))
    updates._prompt_once()
    updates._prompt_once()
    assert updates.available and updates.latestVersion == "0.3.0" and len(calls) == 1
    restarted = module.AppUpdates()
    restarted.prompt.connect(lambda: calls.append(True))
    restarted._prompt_once()
    assert restarted.available and len(calls) == 1
    restarted.setShowPrompts(False)
    assert not restarted.showPrompts and restarted.available


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, "DATA", tmp_path / "data")
    job_path = helper.DATA / "app-updates" / ("a" * 32) / "job.json"
    job_path.parent.mkdir(parents=True)
    old = tmp_path / "App"
    create_application(old, "0.2.0")
    (old / "使用者文件.txt").write_text("必須保留", encoding="utf-8")
    (old / "unins000.dat").write_bytes(b"uninstaller state")
    new = tmp_path / "new"
    create_application(new, "0.3.0")
    archive_application(new, job_path.parent / "update.zip")
    atomic_json(job_path, {"version": "0.3.0", "sha256": sha256(job_path.parent / "update.zip"), "target": str(old), "pid": 123})
    monkeypatch.setattr(helper, "wait_for_parent", lambda *args, **kwargs: None)
    launches = []
    def launch(target, job=None):
        launches.append((Path(target), job))
        return SimpleNamespace(poll=lambda: 0)
    monkeypatch.setattr(helper, "launch_app", launch)
    return job_path, old, launches


def test_update_swap_preserves_user_files_and_previous_installation(job, monkeypatch):
    job_path, old, launches = job
    monkeypatch.setattr(helper, "wait_for_health", lambda *args: True)
    assert helper.apply_job(job_path)
    assert read_json(old / "app-manifest.json", {})["version"] == "0.3.0"
    assert (old / "使用者文件.txt").read_text(encoding="utf-8") == "必須保留"
    assert (old / "unins000.dat").read_bytes() == b"uninstaller state"
    backup = Path(read_json(job_path.parent / "result.json", {})["backup"])
    assert read_json(backup / "app-manifest.json", {})["version"] == "0.2.0"


def test_failed_startup_rolls_back_entire_application(job, monkeypatch):
    job_path, old, launches = job
    monkeypatch.setattr(helper, "wait_for_health", lambda *args: False)
    assert not helper.apply_job(job_path)
    assert read_json(old / "app-manifest.json", {})["version"] == "0.2.0"
    assert read_json(job_path.parent / "result.json", {})["state"] == "rolled_back"
    assert launches[-1] == (old, None)


def test_corrupt_archive_does_not_close_or_modify_running_install(job):
    job_path, old, launches = job
    (job_path.parent / "update.zip").write_bytes(b"corrupt")
    assert not helper.apply_job(job_path)
    assert read_json(old / "app-manifest.json", {})["version"] == "0.2.0"
    assert not launches


def test_helper_refuses_job_outside_owned_cache(tmp_path):
    with pytest.raises(ValueError): helper.validate_job_path(tmp_path / "job.json")
