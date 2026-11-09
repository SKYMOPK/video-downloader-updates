"""Exercise the frozen converter and first-use engine without a system Office install."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.storage import atomic_json,read_json
from app.document_formats import read_text
from app.update_protocol import load_manifest
import pypdfium2 as pdfium

binary=ROOT/'dist/VideoDownloader/VideoDownloader.exe'
data=ROOT/'evidence/document-package-data'
env=dict(os.environ,VD_DATA_DIR=str(data),VD_DISABLE_APP_UPDATE_CHECK='1')
fixtures=ROOT/'evidence/document-fixtures'
report={'cases':[]}
for index,(name,target) in enumerate([('中文報告.docx','pdf'),('試算表.xlsx','pdf'),('簡報.pptx','pdf'),('中文文字.txt','docx'),('透明圖片.png','pdf'),('可選取文字.pdf','txt'),('掃描文件.pdf','txt')]):
    work=ROOT/'evidence'/f'document-package-{index}-{time.time_ns()}'
    work.mkdir()
    atomic_json(work/'job.json',{'sources':[str(fixtures/name)],'output':target})
    started=time.monotonic()
    completed=subprocess.run([str(binary),'--convert-job',str(work/'job.json')],env=env,timeout=230)
    value=read_json(work/'result.json',{})
    expect_ok=name!='掃描文件.pdf'
    assert (completed.returncode==0)==expect_ok and value.get('ok')==expect_ok,(name,value,completed.returncode)
    if expect_ok and target=='pdf':
        with pdfium.PdfDocument(work/'outputs'/value['files'][0]) as pdf:
            assert len(pdf)>0
            if name in ('中文報告.docx','簡報.pptx'): assert len(pdf)==2
    if expect_ok and target=='txt': assert 'Page one' in read_text(work/'outputs'/value['files'][0])
    report['cases'].append({'source':name,'output':target,'expected_success':expect_ok,'result':value,'seconds':round(time.monotonic()-started,2)})
    print(json.dumps(report['cases'][-1],ensure_ascii=True),flush=True)
manifest=load_manifest(binary.parent)
assert len(manifest['files'])<12000,'Must remain compatible with the published 0.2.0 updater'
report['manifest_files']=len(manifest['files'])
report['system_office_required']=False
report['engine_cache_prepared']=any((data/'office-runtime').glob('*/program/soffice.com'))
engine=next((data/'office-runtime').glob('*/program/soffice.com'))
assert (engine.parent/'vcruntime140.dll').is_file(), 'Private VC runtime must be ready without a system install'
bad=ROOT/'evidence'/('document-package-macro-'+str(time.time_ns())); bad.mkdir()
with zipfile.ZipFile(bad/'macro.odt','w') as archive:
    archive.writestr('mimetype','application/vnd.oasis.opendocument.text')
    archive.writestr('Basic/Standard/Module1.xba','fixture macro, never executable')
atomic_json(bad/'job.json',{'sources':[str(bad/'macro.odt')],'output':'pdf'})
completed=subprocess.run([str(binary),'--convert-job',str(bad/'job.json')],env=env,timeout=15)
assert completed.returncode!=0 and '巨集' in read_json(bad/'result.json',{})['error']
report['odf_macro_rejected']=True
atomic_json(ROOT/'evidence/document-package-acceptance.json',report)
fresh=ROOT/'evidence'/('document-startup-fresh-'+str(time.time_ns()))
completed=subprocess.run([str(binary),'--tool','documents','--capture',str(ROOT/'evidence/document-packaged.png'),'--quit-after','7'],env=dict(env,VD_DATA_DIR=str(fresh)),timeout=25)
assert completed.returncode==0
assert (ROOT/'evidence/document-packaged.png').is_file()
assert not (fresh/'office-runtime').exists(), 'App startup must not prepare Office engine'
report['startup_prepares_engine']=False
atomic_json(ROOT/'evidence/document-package-acceptance.json',report)
print('Frozen conversion and document UI accepted.',flush=True)
