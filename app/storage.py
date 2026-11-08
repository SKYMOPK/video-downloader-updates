"""Local-only persistence and collision-safe output paths."""
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
DATA = Path(os.environ.get("VD_DATA_DIR", str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VideoDownloader")))
DEFAULTS = {"folder": str(Path.home() / "Downloads"), "mode": "video", "strategy": "recommended",
            "concurrency": 1, "notifications": True, "reduceMotion": False}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def load_settings():
    stored = read_json(DATA / "settings.json", {})
    settings = DEFAULTS | (stored if isinstance(stored, dict) else {})
    for key in ("notifications", "reduceMotion"):
        if not isinstance(settings[key], bool):
            settings[key] = DEFAULTS[key]
    if settings["mode"] not in ("video", "audio"):
        settings["mode"] = "video"
    if settings["strategy"] not in ("recommended", "best"):
        settings["strategy"] = "recommended"
    if not isinstance(settings["folder"], str) or not settings["folder"]:
        settings["folder"] = DEFAULTS["folder"]
    try:
        settings["concurrency"] = max(1, min(3, int(settings["concurrency"])))
    except (TypeError, ValueError):
        settings["concurrency"] = 1
    return settings


def tool(name):
    if name == "yt-dlp":
        active = read_json(DATA / "core-active.json", {})
        version = active.get("version", "") if isinstance(active, dict) else ""
        if re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}(?:\.[0-9]+)?", version):
            candidate = DATA / "cores" / version / "yt-dlp.exe"
            if candidate.is_file():
                return str(candidate)
    return str(ROOT / "tools" / (name + ".exe"))


def safe_filename(title, video_id=""):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(title)).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        name = "影片_" + (video_id or "未命名")
    return trim_utf16(name,120).rstrip(" .")


def trim_utf16(value,units):
    result=[]
    used=0
    for char in value:
        count=2 if ord(char)>0xffff else 1
        if used+count>units: break
        result.append(char)
        used+=count
    return "".join(result)


def publish(source, folder, title, video_id):
    """Atomic same-volume publication, never replace an existing file."""
    source, folder = Path(source), Path(folder)
    base = safe_filename(title, video_id)
    # Keep below conservative legacy Windows path budgets, including suffix.
    folder_units=len(str(folder.resolve()).encode("utf-16-le"))//2
    budget = min(120, 235 - folder_units - len(source.suffix) - 12)
    if budget < 12:
        raise OSError("儲存位置路徑太長，請選擇較短的資料夾")
    base = trim_utf16(base,budget).rstrip(" .")
    for number in range(10000):
        suffix = f" ({number})" if number else ""
        target = folder / f"{base}{suffix}{source.suffix}"
        try:
            if os.name == "nt":
                os.rename(source, target)  # Windows rename does not replace.
            else:
                os.link(source, target)
                source.unlink()
            return str(target)
        except FileExistsError:
            continue
    raise OSError("同名檔案過多，請選擇其他資料夾")


def workspace(folder, task_id):
    path = Path(folder) / ".video-downloader" / task_id
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".owner.json"
    if not marker.exists():
        atomic_json(marker, {"app": "VideoDownloader", "task": task_id, "created": time.time()})
    registry = read_json(DATA / "workspaces.json", [])
    registry = registry if isinstance(registry,list) else []
    if str(path.resolve()) not in registry:
        registry.append(str(path.resolve()))
        atomic_json(DATA / "workspaces.json", registry)
    return path
