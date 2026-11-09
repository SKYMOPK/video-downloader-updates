"""Verify this package with the exact validator shipped in 0.2.0."""
import json
from pathlib import Path
import sys
import time
import types
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.storage import atomic_json
from app.release import VERSION

source=ROOT/'dist/VideoDownloader-0.2.0-source.zip'
assert source.is_file(),'Published source archive required for backward compatibility test'
with zipfile.ZipFile(source) as archive:
    content=archive.read('video-downloader/app/update_protocol.py')
old=types.ModuleType('published_020_validator')
exec(compile(content,'published_0.2.0_update_protocol.py','exec'),old.__dict__)
target=ROOT/('work-document-update-compatibility-'+str(time.time_ns()))
package=ROOT/f'dist/VideoDownloader-{VERSION}-win64-update.zip'
assert package.stat().st_size<=old.MAX_DOWNLOAD
started=time.monotonic()
manifest=old.extract_package(package,target,VERSION)
assert (target/'_internal/tools/office-runtime.zip').is_file()
report={'validator_version':'0.2.0','target_version':VERSION,'archive_bytes':package.stat().st_size,'manifest_files':len(manifest['files']),
        'full_hash_validation':True,'seconds':round(time.monotonic()-started,2),'extracted':str(target)}
atomic_json(ROOT/'evidence/document-update-compatibility.json',report)
print(json.dumps(report,ensure_ascii=True),flush=True)
