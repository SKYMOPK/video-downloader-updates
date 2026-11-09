"""Extract a verified official LibreOffice MSI into a private bundled runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile


def archive_runtime(target, marker):
    archive = ROOT/'tools/office-runtime.zip'
    info = json.loads(marker.read_text(encoding='utf-8'))
    if archive.is_file() and info.get('runtime_sha256'): return
    print('Packaging private Office runtime…',flush=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as package:
        for path in sorted(target.rglob('*')):
            if path.is_file(): package.write(path,path.relative_to(target).as_posix())
    with archive.open('rb') as stream: info['runtime_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    marker.write_text(json.dumps(info,indent=2),encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
VERSION = "26.8.2"
SHA256 = "ff4b911403b67ee9e6249f820f9782c44bb32c94fdaa45b0da53a8e419e5307a"
URL = f"https://download.documentfoundation.org/libreoffice/stable/{VERSION}/win/x86_64/LibreOffice_{VERSION}_Win_x86-64.msi"


def bootstrap():
    target = ROOT / "tools/office"
    marker = ROOT / "tools/office-manifest.json"
    if (target / "program/soffice.com").is_file() and marker.is_file():
        print("Bundled Office engine already present.", flush=True)
        archive_runtime(target,marker)
        return
    cache = ROOT / "build-tools" / f"LibreOffice_{VERSION}.msi"
    cache.parent.mkdir(exist_ok=True)
    if not cache.exists():
        print("Downloading verified official LibreOffice engine…", flush=True)
        with urllib.request.urlopen(URL, timeout=120) as response, cache.open("wb") as output:
            while chunk := response.read(1024 ** 2): output.write(chunk)
    with cache.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != SHA256:
            raise ValueError("LibreOffice installer SHA256 mismatch")
    extracted = ROOT / "build-tools/office-extracted"
    command = f'msiexec.exe /a "{cache}" /qn TARGETDIR="{extracted}" /L*v "{ROOT / "evidence/office-extraction.log"}"'
    result = subprocess.run(command, timeout=240)
    if result.returncode not in (0, 3010): raise RuntimeError(f"Office administrative extraction failed: {result.returncode}")
    candidates = list(extracted.rglob("program/soffice.com"))
    if len(candidates) != 1: raise RuntimeError("Office engine location is ambiguous")
    import shutil
    shutil.copytree(candidates[0].parent.parent, target, dirs_exist_ok=True)
    info = {"version": VERSION, "source": URL, "artifact_sha256": SHA256,
            "soffice_sha256": hashlib.file_digest((target / "program/soffice.com").open("rb"), "sha256").hexdigest()}
    marker.write_text(json.dumps(info, indent=2), encoding="utf-8")
    archive_runtime(target,marker)
    print("Official Office runtime extracted without system installation.", flush=True)


if __name__ == "__main__": bootstrap()
