"""Exercise legacy and OpenDocument input routes with real generated files."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.document_engine import ensure_office,run_job
from app.storage import atomic_json,read_json
import pypdfium2 as pdfium

work=ROOT/('work-document-matrix-'+str(time.time_ns())); work.mkdir()
fixtures=ROOT/'evidence/document-fixtures'
report=[]
for index,(name,kind) in enumerate([('中文報告.docx','doc'),('中文報告.docx','rtf'),('中文報告.docx','odt'),('試算表.xlsx','xls'),('試算表.xlsx','ods'),('簡報.pptx','ppt'),('簡報.pptx','odp')]):
    folder=work/str(index); folder.mkdir()
    profile=folder/'fixture-profile'
    result=subprocess.run([str(ensure_office()),'-env:UserInstallation='+profile.as_uri(),'--headless','--norestore','--convert-to',kind,'--outdir',str(folder),str(fixtures/name)],capture_output=True,timeout=90)
    source=folder/(Path(name).stem+'.'+kind)
    assert result.returncode==0 and source.is_file(),(name,kind,result.stdout,result.stderr)
    job=folder/'conversion'; job.mkdir()
    atomic_json(job/'job.json',{'sources':[str(source)],'output':'pdf'})
    assert run_job(job/'job.json')==0,read_json(job/'result.json',{})
    value=read_json(job/'result.json',{})
    with pdfium.PdfDocument(job/'outputs'/value['files'][0]) as pdf:
        assert len(pdf)>0
        report.append({'input':kind,'output':'pdf','pages':len(pdf),'ok':True})
    print(json.dumps(report[-1]),flush=True)
atomic_json(ROOT/'evidence/document-office-matrix.json',report)
