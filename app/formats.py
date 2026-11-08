"""Pure format normalization and explicit conversion planning."""
from urllib.parse import urlparse, parse_qs
import re


class UserError(Exception):
    pass


def normalize_url(value):
    value = value.strip()
    if len(value) > 4096:
        raise UserError("網址過長，請貼上影片的分享連結")
    if not value.startswith(("https://", "http://")):
        value = "https://" + value
    try:
        p = urlparse(value)
        port=p.port
    except ValueError:
        raise UserError("網址格式不正確，請重新貼上影片分享連結") from None
    if p.username or p.password or port not in (None, 80, 443):
        raise UserError("請使用一般 YouTube 影片網址")
    host = (p.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        video_id = p.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"):
        parts = p.path.strip("/").split("/")
        video_id = parse_qs(p.query).get("v", [""])[0] if p.path == "/watch" else (parts[1] if len(parts) > 1 and parts[0] in ("shorts", "embed", "live", "v") else "")
    else:
        raise UserError("目前支援 YouTube 影片，請確認網址")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise UserError("找不到有效的影片編號，請貼上單部影片網址")
    return "https://www.youtube.com/watch?v=" + video_id


def codec_name(codec):
    value = str(codec or "")
    for prefix, label in (("avc", "H.264"), ("h264", "H.264"), ("hev", "HEVC"), ("hvc", "HEVC"), ("av01", "AV1"), ("av1", "AV1"), ("vp9", "VP9"), ("vp09", "VP9"), ("mp4a", "AAC"), ("aac", "AAC"), ("opus", "Opus"), ("vorbis", "Vorbis")):
        if value.startswith(prefix):
            return label
    return value.upper() if value and value != "none" else "未知"


def size_text(size):
    if not size or size <= 0:
        return "大小未知"
    if size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 ** 3:.2f} GB" if size >= 1024 ** 3 else f"{size / 1024 ** 2:.1f} MB"


def normalize(info):
    if info.get("is_live") or info.get("live_status") == "is_upcoming":
        raise UserError("目前不支援直播中或尚未開始的影片，請在回放公開後再試")
    video, audio = [], []
    for f in info.get("formats", []):
        if f.get("has_drm") or not f.get("url"):
            continue
        vc, ac = f.get("vcodec", "none"), f.get("acodec", "none")
        if vc not in (None, "none") and f.get("height"):
            height, fps = int(f["height"]), float(f.get("fps") or 0)
            label = f"{height}p" + (f" · {fps:g} FPS" if fps else "") + f" · {codec_name(vc)} · {str(f.get('ext', '')).upper()}"
            video.append({"id": str(f["format_id"]), "height": height, "fps": fps, "vcodec": vc,
                          "acodec": ac, "ext": f.get("ext", ""), "label": label,
                          "size": f.get("filesize") or f.get("filesize_approx") or 0,
                          "tbr": float(f.get("tbr") or 0)})
        elif ac not in (None, "none") and vc in (None, "none"):
            audio.append({"id": str(f["format_id"]), "acodec": ac, "ext": f.get("ext", ""),
                          "abr": float(f.get("abr") or f.get("tbr") or 0),
                          "language": f.get("language") or "", "note": f.get("format_note") or "", "channels": f.get("audio_channels") or 0,
                          "preference": float(f.get("language_preference") or 0),
                          "size": f.get("filesize") or f.get("filesize_approx") or 0})
    video.sort(key=lambda f: (f["height"], f["fps"], f["tbr"]), reverse=True)
    # Deduplicate equivalent streams while retaining distinct codec/FPS choices.
    seen, unique = set(), []
    for f in video:
        key = (f["height"], f["fps"], codec_name(f["vcodec"]), f["ext"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    audio.sort(key=lambda f: (f["preference"], f["abr"]), reverse=True)
    if not unique and not audio:
        raise UserError("沒有可使用的影音串流；來源可能受到限制，或下載核心需要更新")
    seconds = int(info.get("duration") or 0)
    duration = f"{seconds // 3600}:{seconds % 3600 // 60:02}:{seconds % 60:02}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02}"
    date = str(info.get("upload_date") or "")
    date = f"{date[:4]}/{date[4:6]}/{date[6:8]}" if len(date) == 8 else ""
    return {"id": info.get("id", ""), "url": info.get("webpage_url", ""), "title": info.get("title") or "未命名影片",
            "channel": info.get("channel") or info.get("uploader") or "未知頻道", "duration": duration,
            "thumbnail": info.get("thumbnail") or "", "date": date, "videos": unique, "audios": audio,
            "license": info.get("license") or "", "type": "YouTube", "seconds": seconds}


def recommended_index(videos):
    return next((i for i, f in enumerate(videos) if codec_name(f["vcodec"]) == "H.264"), 0)


def video_choices(videos, container="mp4"):
    """One choice per resolution/frame rate; retain raw streams for planning."""
    groups = {}
    codec_order = ("VP9", "AV1", "VP8") if container == "webm" else ("H.264", "HEVC", "AV1", "VP9", "VP8")
    for index, video in enumerate(videos):
        key = (video["height"], round(video["fps"]))
        codec = codec_name(video["vcodec"])
        rank = (codec_order.index(codec) if codec in codec_order else len(codec_order), -video.get("tbr", 0))
        if key not in groups or rank < groups[key][0]:
            groups[key] = (rank, index)
    choices = []
    for (height, fps), (_, index) in sorted(groups.items(), reverse=True):
        description = ("8K 極清晰" if height >= 4320 else "4K 極清晰" if height >= 2160
                       else "2K 超清晰" if height >= 1440 else "超清晰" if height >= 1080
                       else "高清晰" if height >= 720 else "標準畫質" if height >= 480 else "省空間")
        frame_rate = f" · 流暢 {fps} fps" if fps > 30 else (f" · {fps} fps" if fps and fps != 30 else "")
        label = f"{height}p · {description}" + frame_rate
        choices.append({"index": index, "label": label})
    return choices


def plan(media, mode, video_index, container, audio_format, bitrate, audio_index=0):
    audios, videos = media.get("audios", []), media.get("videos", [])
    audio = audios[max(0, min(audio_index, len(audios)-1))] if audios else None
    bitrate = int(bitrate) if str(bitrate).isdigit() else 192
    if bitrate not in (128, 192, 256, 320):
        raise UserError("輸出位元率不在支援範圍內")
    if mode == "audio":
        if not audio:
            raise UserError("來源沒有獨立音訊串流，請改用影片模式")
        if audio_format not in ("original", "mp3", "m4a", "opus", "wav"):
            raise UserError("請選擇有效的音訊格式")
        ext = audio["ext"] if audio_format == "original" else audio_format
        codec = codec_name(audio["acodec"])
        copy = audio_format == "original" or (audio_format == "m4a" and codec == "AAC") or (audio_format == "opus" and codec == "Opus")
        return {"selector": audio["id"], "ext": ext, "mode": mode, "transcode": not copy,
                "bitrate": bitrate, "height": 0, "fps": 0, "sourceAudio": codec,
                "summary": f"{ext.upper()} · " + ("保留來源音訊" if copy else ("PCM 無壓縮輸出" if ext == "wav" else f"轉換為 {bitrate} kbps"))}
    if mode != "video" or not videos or container not in ("mp4", "mkv", "webm"):
        raise UserError("請選擇有效的影片規格")
    if not 0 <= video_index < len(videos):
        raise UserError("所選畫質已不可用，請重新選擇")
    video = videos[video_index]
    has_audio = video["acodec"] not in (None, "none")
    if not has_audio and not audio:
        raise UserError("此影片沒有可搭配的音訊串流")
    # Respect explicit audio-track choice. Never silently change its language.
    vc = codec_name(video["vcodec"])
    ac = codec_name(video["acodec"] if has_audio else audio["acodec"])
    if container == "webm" and (vc not in ("VP9", "AV1", "VP8") or ac not in ("Opus", "Vorbis")):
        raise UserError("WebM 需要 VP8／VP9／AV1 與 Opus／Vorbis，請選其他來源或改用 MKV")
    transcode = container == "mp4" and (vc not in ("H.264", "HEVC", "AV1") or ac != "AAC")
    return {"selector": video["id"] if has_audio else video["id"] + "+" + audio["id"],
            "ext": container, "mode": mode, "transcode": transcode, "bitrate": bitrate,
            "height": video["height"], "fps": video["fps"], "sourceAudio": ac,
            "summary": f"{video['height']}p · {video['fps']:g} FPS · {container.upper()} · " + ("需重新編碼" if transcode else ("重新封裝" if has_audio else "合併影音，不重新編碼"))}


def classify_error(text):
    lower = text.lower()
    groups = [(("no space", "disk full", "空間不足", "errno 28"), "磁碟空間不足，請釋放空間或更換儲存位置", False),
              (("permission denied", "access is denied", "errno 13"), "無法寫入檔案，請確認資料夾權限及檔案是否被占用", False),
              (("private video", "members-only", "sign in", "age-restricted", "not available in your country", "403", "429"), "來源要求登入或受到存取限制；請稍後再試或改用可正常存取的公開影片", False),
              (("video unavailable", "removed", "not found"), "影片不存在、已移除或目前無法存取", False),
              (("requested format", "no video formats", "format is not available"), "所選來源格式已不可用，請重新解析並選擇其他規格", False),
              (("timed out", "timeout", "connection reset", "temporary failure", "network is unreachable", "unable to download", "urlopen error"), "網路連線中斷或逾時，請檢查連線後重試", True),
              (("javascript", "challenge", "signature", "nsig"), "來源解析未成功，請檢查下載核心與 JavaScript 元件更新", False),
              (("ffmpeg", "conversion failed", "invalid data"), "影音處理失敗，已保留可恢復資料；請查看診斷資訊", False)]
    for needles, message, retry in groups:
        if any(needle in lower for needle in needles):
            return message, retry
    return "目前無法完成此任務。請重試、重新解析，或查看診斷資訊", False
