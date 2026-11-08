"""Fetch traceable Windows sidecars. Run explicitly during build, never on startup."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TOOLS.mkdir(exist_ok=True)


def fetch(url, dest=None):
    req = urllib.request.Request(url, headers={"User-Agent": "VideoDownloader-Build/0.1"})
    with urllib.request.urlopen(req, timeout=180) as response:
        if dest:
            with open(dest, "wb") as stream:
                shutil.copyfileobj(response, stream)
            return Path(dest).read_bytes() if str(dest).endswith(".json") else None
        return response.read()


def github_binary(repo, asset_name, output, zipped=False):
    release = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))
    asset = next(a for a in release["assets"] if a["name"] == asset_name)
    target = TOOLS / (asset_name if zipped else output)
    if not (TOOLS / output).exists():
        print(f"Downloading {repo} {release['tag_name']}...", flush=True)
        fetch(asset["browser_download_url"], target)
    if zipped and target.exists():
        with zipfile.ZipFile(target) as archive:
            with archive.open(output) as source, open(TOOLS / output, "wb") as dest:
                shutil.copyfileobj(source, dest)
    artifact = target if target.exists() else TOOLS / output
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    expected = asset.get("digest")
    if expected and expected != f"sha256:{digest}":
        raise RuntimeError(f"Hash mismatch: {asset_name}")
    if not expected and repo == "yt-dlp/yt-dlp":
        sums = fetch(f"https://github.com/{repo}/releases/download/{release['tag_name']}/SHA2-256SUMS").decode()
        official = next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*') == asset_name)
        if digest != official:
            raise RuntimeError("yt-dlp SHA256 mismatch")
    return {"name": output, "version": release["tag_name"], "source": asset["browser_download_url"],
            "artifact_sha256": digest, "sha256": hashlib.sha256((TOOLS / output).read_bytes()).hexdigest()}


def ffmpeg():
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    archive_path = TOOLS / "ffmpeg-release-essentials.zip"
    if not (TOOLS / "ffprobe.exe").exists():
        print("Downloading FFmpeg essentials...", flush=True)
        fetch(url, archive_path)
        expected = fetch(url + ".sha256").decode().split()[0]
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError("FFmpeg SHA256 mismatch")
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if name.endswith(("/bin/ffmpeg.exe", "/bin/ffprobe.exe", "/LICENSE")):
                    with archive.open(name) as source, open(TOOLS / Path(name).name, "wb") as dest:
                        shutil.copyfileobj(source, dest)
        (TOOLS / "ffmpeg-archive.sha256").write_text(digest)
    return [{"name": name, "source": url, "sha256": hashlib.sha256((TOOLS / name).read_bytes()).hexdigest()}
            for name in ("ffmpeg.exe", "ffprobe.exe")]


def restore_pinned():
    manifest = json.loads((TOOLS / "manifest.json").read_text())
    for entry in manifest:
        dest = TOOLS / entry["name"]
        if dest.parent != TOOLS or Path(entry["name"]).name != entry["name"]:
            raise ValueError("Invalid tool path")
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        source = entry["source"]
        if entry["name"] == "yt-dlp.exe":
            fetch(source, dest)
        else:
            archive_path = TOOLS / ("deno-pinned.zip" if entry["name"] == "deno.exe" else "ffmpeg-pinned.zip")
            if not archive_path.exists():
                fetch(source, archive_path)
            if entry.get("artifact_sha256") and hashlib.sha256(archive_path.read_bytes()).hexdigest() != entry["artifact_sha256"]:
                raise ValueError("Pinned archive hash mismatch")
            with zipfile.ZipFile(archive_path) as archive:
                name = next(name for name in archive.namelist() if Path(name).name == entry["name"])
                with archive.open(name) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Pinned tool hash mismatch: " + entry["name"])
    print("Pinned sidecars verified", flush=True)


if __name__ == "__main__" and (TOOLS / "manifest.json").exists() and "--refresh" not in sys.argv:
    restore_pinned()
elif __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(github_binary, "yt-dlp/yt-dlp", "yt-dlp.exe", "yt-dlp.exe"),
                pool.submit(github_binary, "denoland/deno", "deno-x86_64-pc-windows-msvc.zip", "deno.exe", True),
                pool.submit(ffmpeg)]
        results = [job.result() for job in jobs]
    flattened = [item for result in results for item in (result if isinstance(result, list) else [result])]
    (TOOLS / "manifest.json").write_text(json.dumps(flattened, indent=2), encoding="utf-8")
    print("Sidecars ready; provenance saved to tools/manifest.json", flush=True)
