"""Install, launch, upgrade, uninstall in an explicitly workspace-owned target.

Runs installer directly, with no UI automation or external user data deletion.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import sys
import psutil
import winreg

ROOT=Path(__file__).resolve().parents[1]
target=(ROOT/"work-install-test").resolve()
assert target.parent==ROOT.resolve() and target.name=="work-install-test"
try:
    key=winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{0A065A63-454A-44CC-A06B-3B22BDCE2F18}_is1",0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY)
    with key:
        installed_at=winreg.QueryValueEx(key,"InstallLocation")[0]
    if Path(installed_at).resolve()!=target:
        raise RuntimeError("已有非測試用途的安裝，請先使用獨立測試帳戶或虛擬機，避免取代使用者版本")
except FileNotFoundError:
    pass
installer=ROOT/"dist/VideoDownloader-0.1.0-win64-setup.exe"
data=ROOT/"work-installed-data"
env=os.environ.copy()
env["VD_DATA_DIR"]=str(data)
report={"environment":sys.getwindowsversion().build,"clean_vm":False,"target":str(target),"stages":[]}
def run(args):
    result=subprocess.run([str(arg) for arg in args],timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode: raise RuntimeError(f"command exit {result.returncode}: {args[0]}")
run([installer,"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART",f"/DIR={target}",f"/LOG={ROOT/'evidence/install.log'}"])
report["stages"].append({"stage":"install","ok":(target/"VideoDownloader.exe").is_file()})
start=time.perf_counter()
process=subprocess.Popen([str(target/"VideoDownloader.exe"),"--capture",str(ROOT/"evidence/installed-startup.png"),"--quit-after","16"],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
handle=psutil.Process(process.pid)
cpu=[];memory=[]
while process.poll() is None:
    try:
        all_procs=[handle]+handle.children(recursive=True)
        memory.append(sum(p.memory_info().rss for p in all_procs if p.is_running()))
        if time.perf_counter()-start>6:
            before=handle.cpu_times()
            time.sleep(1)
            after=handle.cpu_times()
            cpu.append(((after.user+after.system)-(before.user+before.system))*100)
        else:time.sleep(0.2)
    except psutil.NoSuchProcess:break
report["stages"].append({"stage":"launch","ok":process.wait()==0 and (ROOT/"evidence/installed-startup.png").exists()})
report["metrics"]={"idle_cpu_single_core_percent":sum(cpu)/len(cpu) if cpu else None,"peak_rss_mib":max(memory)/1024**2 if memory else None,
                   "installed_mib":sum(p.stat().st_size for p in target.rglob('*') if p.is_file())/1024**2,
                   "installer_mib":installer.stat().st_size/1024**2}
# Native UI interaction is performed separately while this real installed app runs.
settings={"folder":str(ROOT/"evidence/installed-downloads"),"notifications":False}
data.mkdir(parents=True,exist_ok=True)
(data/"settings.json").write_text(json.dumps(settings),encoding="utf-8")
network=subprocess.Popen([str(target/"VideoDownloader.exe"),"--url","https://www.youtube.com/watch?v=aqz-KE-bpKQ","--capture",str(ROOT/"evidence/installed-parsing.png"),"--quit-after","600"],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
network.wait(timeout=640)
tasks_file=data/"tasks.json"
tasks=json.loads(tasks_file.read_text(encoding="utf-8")) if tasks_file.exists() else []
report["stages"].append({"stage":"installed-real-network-ui-download","ok":bool(tasks) and all(t["state"]=="completed" for t in tasks),
                          "tasks":[{k:t.get(k) for k in ("state","path","error","plan")} for t in tasks]})
# Upgrade same version verifies file replacement and preservation; not migration.
data.mkdir(exist_ok=True)
sentinel=data/"preserve-test.txt"
sentinel.write_text("User preference preservation sentinel")
run([installer,"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART",f"/DIR={target}",f"/LOG={ROOT/'evidence/upgrade.log'}"])
report["stages"].append({"stage":"same-version-reinstall","ok":sentinel.is_file()})
uninstaller=target/"unins000.exe"
assert uninstaller.parent==target and target.parent==ROOT.resolve()
run([uninstaller,"/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART",f"/LOG={ROOT/'evidence/uninstall.log'}"])
report["stages"].append({"stage":"uninstall","ok":not (target/"VideoDownloader.exe").exists() and sentinel.is_file()})
(ROOT/"evidence/package-acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
