import json
from pathlib import Path
import pytest

from app.formats import normalize_url, normalize, plan, recommended_index, classify_error, UserError
from app.storage import safe_filename, publish, atomic_json, read_json, workspace
from app.formats import video_choices


@pytest.mark.parametrize("url", ["https://youtu.be/aqz-KE-bpKQ?t=1", "youtube.com/watch?v=aqz-KE-bpKQ&list=PLxxx", "https://m.youtube.com/watch?v=aqz-KE-bpKQ", "https://www.youtube.com/shorts/aqz-KE-bpKQ", "https://www.youtube-nocookie.com/embed/aqz-KE-bpKQ"])
def test_urls(url):
    assert normalize_url(url) == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


@pytest.mark.parametrize("url", ["https://youtube.com.evil.com/watch?v=aqz-KE-bpKQ", "https://user:pass@youtube.com/watch?v=aqz-KE-bpKQ", "--exec calc.exe", "https://www.youtube.com/playlist?list=PL", "https://youtu.be/nope", "https://youtube.com:444/watch?v=aqz-KE-bpKQ"])
def test_reject_urls(url):
    with pytest.raises((UserError, ValueError)): normalize_url(url)


@pytest.fixture
def media():
    return normalize({"id": "aqz-KE-bpKQ", "title": "中文／測試", "duration": 65, "formats": [
        {"format_id": "v4k", "url": "https://test", "vcodec": "av01", "acodec": "none", "height": 2160, "fps": 60, "ext": "mp4", "tbr": 10000},
        {"format_id": "v1080", "url": "https://test", "vcodec": "avc1", "acodec": "none", "height": 1080, "fps": 30, "ext": "mp4", "tbr": 1000},
        {"format_id": "drm", "url": "https://test", "vcodec": "avc1", "height": 4320, "has_drm": True},
        {"format_id": "aac", "url": "https://test", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "ext": "m4a"},
        {"format_id": "opus", "url": "https://test", "vcodec": "none", "acodec": "opus", "abr": 160, "ext": "webm"}]})


def test_formats_and_defaults(media):
    assert media["duration"] == "1:05"
    assert len(media["videos"]) == 2
    assert media["videos"][0]["height"] == 2160
    assert recommended_index(media["videos"]) == 1


def test_quality_choices_merge_codecs_but_preserve_60fps():
    videos = [
        {"height": 1080, "fps": 60, "vcodec": "vp9", "tbr": 3000},
        {"height": 1080, "fps": 59.94, "vcodec": "avc1", "tbr": 2000},
        {"height": 1080, "fps": 30, "vcodec": "avc1", "tbr": 1000},
        {"height": 480, "fps": 30, "vcodec": "vp9", "tbr": 500},
        {"height": 480, "fps": 30, "vcodec": "avc1", "tbr": 600},
    ]
    choices = video_choices(videos)
    assert len(choices) == 3
    assert choices[0]["index"] == 1 and "60 fps" in choices[0]["label"]
    assert choices[2]["label"] == "480p · 標準畫質"
    assert video_choices(videos, "webm")[0]["index"] == 0


def test_webm_compatibility(media):
    with pytest.raises(UserError): plan(media, "video", 1, "webm", "original", 192)
    assert not plan(media, "video", 0, "webm", "original", 192, 0)["transcode"]


def test_mp4_audio_conversion_is_explicit(media):
    assert plan(media, "video", 1, "mp4", "original", 192, 0)["transcode"]
    assert not plan(media, "video", 1, "mp4", "original", 192, 1)["transcode"]


def test_original_audio_and_lossy_output(media):
    assert not plan(media, "audio", 0, "mp4", "original", 192)["transcode"]
    assert plan(media, "audio", 0, "mp4", "mp3", 320)["transcode"]
    assert plan(media, "audio", 0, "mp4", "wav", 192)["ext"] == "wav"


@pytest.mark.parametrize("name", ["CON", "NUL.txt", "COM1", "LPT9.txt", "<bad>:?*", "中文😀標題", "最後有句點. "])
def test_filenames(name):
    result = safe_filename(name, "test")
    assert result and not result.endswith((" ", "."))
    assert not any(c in result for c in '<>:"/\\|?*')
    assert result.split(".")[0].upper() not in ("CON", "NUL", "COM1", "LPT9")


def test_output_never_overwrites(tmp_path):
    (tmp_path / "影片.mp4").write_bytes(b"existing")
    work = tmp_path / "owned"
    work.mkdir()
    source = work / "output.mp4"
    source.write_bytes(b"new")
    dest = publish(source, tmp_path, "影片", "id")
    assert Path(dest).name == "影片 (1).mp4"
    assert (tmp_path / "影片.mp4").read_bytes() == b"existing"
    assert Path(dest).read_bytes() == b"new"


def test_storage_corruption_and_atomic_write(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken")
    assert read_json(path, {}) == {}
    atomic_json(path, {"資料夾": "中文"})
    assert read_json(path, {}) == {"資料夾": "中文"}
    assert not path.with_suffix(".tmp").exists()


def test_workspace_ownership_marker(tmp_path):
    work = workspace(tmp_path, "abcdef")
    marker = read_json(work / ".owner.json", {})
    assert marker["task"] == "abcdef" and marker["app"] == "VideoDownloader"


@pytest.mark.parametrize("message,retry", [("Connection timed out", True), ("HTTP Error 403", False), ("No space left on device", False), ("Requested format is not available", False), ("Sign in to confirm your age", False)])
def test_error_retry_policy(message, retry):
    localized, actual = classify_error(message)
    assert actual is retry and localized != message


def test_live_is_not_downloaded():
    with pytest.raises(UserError): normalize({"is_live": True, "formats": []})


def test_emoji_filename_uses_utf16_budget():
    assert len(safe_filename("😀"*200).encode("utf-16-le"))//2 <= 120
