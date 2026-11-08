"""Exercise real official core check/install/parse/rollback in isolated app data."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
os.environ["VD_DATA_DIR"]=str(ROOT/"work-update-data")
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QCoreApplication,QTimer
from app.updater import UpdateWorker
from app.storage import DATA,atomic_json,tool
from app.engine import core_args
from app.process import ManagedProcess
app=QCoreApplication([])
workers=[]
report={"stages":[],"errors":[]}
latest=[""]
success=[False]

def check_result(ok,version,message):
    report["stages"].append({"stage":"check","ok":ok,"version":version,"message":message})
    latest[0]=version if ok else ""

def checked():
    if not latest[0]: app.quit();return
    install=UpdateWorker(True,latest[0],app)
    workers.append(install)
    install.result.connect(installed_result)
    install.finished.connect(installed)
    install.start()

def installed_result(ok,version,message):
    report["stages"].append({"stage":"install","ok":ok,"version":version,"message":message})
    success[0]=ok

def installed():
    if not success[0]:app.quit();return
    probe=ManagedProcess(tool("yt-dlp"),core_args()+["--skip-download","--dump-single-json","--","https://www.youtube.com/watch?v=aqz-KE-bpKQ"],app)
    workers.append(probe)
    def parsed(code,output):
        ok=code==0 and any(line.startswith('{') for line in output.splitlines())
        report["stages"].append({"stage":"new-core-with-bundled-deno-parse","ok":ok})
        atomic_json(DATA/"core-active.json",{})
        report["stages"].append({"stage":"rollback-to-bundled","ok":Path(tool('yt-dlp')).resolve()==(ROOT/'tools/yt-dlp.exe').resolve()})
        (ROOT/"evidence/update-acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        app.quit()
    probe.done.connect(parsed)
    probe.start()
check=UpdateWorker(False,parent=app)
workers.append(check)
check.result.connect(check_result)
check.finished.connect(checked)
QTimer.singleShot(0,check.start)
app.exec()
print(json.dumps(report,ensure_ascii=False,indent=2))
