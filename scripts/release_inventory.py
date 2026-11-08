"""Create a small reproducible source archive and artifact checksum inventory."""
import hashlib
import json
from pathlib import Path
import zipfile
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.release import VERSION

def digest(path):
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024**2),b""):
            value.update(chunk)
    return value.hexdigest()

if __name__=="__main__":
    source=ROOT/f"dist/VideoDownloader-{VERSION}-source.zip"
    paths=[]
    for directory in ("app","qml","assets","scripts","tests","docs","packaging"):
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for name in ("main.py","pyproject.toml","uv.lock","requirements-lock.txt","README.md","THIRD_PARTY_NOTICES.md","VideoDownloader.spec","installer.iss",".gitignore",".python-version","tools/manifest.json","tools/LICENSE"):
        paths.append(ROOT/name)
    evidence_names=("pytest.txt","compatibility.json","integration-video.json","integration-audio.json","ui-acceptance.json","update-acceptance.json",
                    "package-acceptance.json","package-interruption.json","performance-probe.json","installed-output-validation.json","final-package-smoke.json","input-acceptance.json","refinement-packaged.json","app-update-ui.json","app-update-integration.json","app-update-installer.json")
    def redact(value):
        if isinstance(value,str):return value.replace(str(ROOT),"<PROJECT>").replace(str(Path.home()),"<USER>")
        if isinstance(value,list):return [redact(v) for v in value]
        if isinstance(value,dict):return {k:redact(v) for k,v in value.items()}
        return value
    with zipfile.ZipFile(source,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path,"video-downloader/"+path.relative_to(ROOT).as_posix())
        for name in evidence_names:
            path=ROOT/"evidence"/name
            if not path.is_file():continue
            text=path.read_text(encoding="utf-8-sig")
            if path.suffix==".json":text=json.dumps(redact(json.loads(text)),ensure_ascii=False,indent=2)
            else:text=redact(text)
            archive.writestr("video-downloader/evidence/"+name,text)
    artifacts=[source,ROOT/f"dist/VideoDownloader-{VERSION}-win64-setup.exe",ROOT/f"dist/VideoDownloader-{VERSION}-win64-update.zip",ROOT/"dist/VideoDownloader/VideoDownloader.exe"]
    inventory={"artifacts":[{"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":digest(p)} for p in artifacts],
               "source_files":[{"path":p.relative_to(ROOT).as_posix(),"sha256":digest(p)} for p in sorted(paths)]}
    (ROOT/"dist/SHA256.json").write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(inventory["artifacts"],indent=2))
