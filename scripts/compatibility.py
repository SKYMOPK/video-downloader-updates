"""Public metadata compatibility survey. Does not download video data.

Only explicitly CC-labelled samples count toward the authorized-source matrix.
Keep extraction statistics distinct from download/output statistics.
"""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.formats import normalize
from app.storage import tool
from app.engine import core_args


def inspect(entry):
    vid = entry["id"]
    url = "https://www.youtube.com/watch?v=" + vid
    command = [tool("yt-dlp"), *core_args(), "--skip-download", "--dump-single-json", "--", url]
    start = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, timeout=100, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = result.stdout.decode("utf-8", errors="replace")
        if result.returncode: raise ValueError(result.stderr.decode("utf-8",errors="replace")[-500:])
        raw = json.loads(next(line for line in reversed(text.splitlines()) if line.startswith("{")))
        media = normalize(raw)
        cc = "Creative Commons" in media["license"]
        return {"id":vid,"url":url,"title":media["title"],"license":media["license"],"authorized_sample":cc,
                "parse":True,"seconds":round(time.monotonic()-start,2),"duration":media["seconds"],
                "heights":sorted({v["height"] for v in media["videos"]}),"fps":sorted({v["fps"] for v in media["videos"]}),
                "video_codecs":sorted({v["vcodec"].split('.')[0] for v in media["videos"]}),
                "audio_codecs":sorted({a["acodec"].split('.')[0] for a in media["audios"]}),
                "shorts":entry.get("shorts",False),"download":"not attempted","output":"not attempted"}
    except Exception as exc:
        return {"id":vid,"url":url,"parse":False,"authorized_sample":False,"error":str(exc)}


if __name__ == "__main__":
    for filename,suffix,count in (("evidence-channel.json","videos",50),("evidence-shorts.json","shorts",6)):
        path=ROOT/filename
        if not path.exists():
            result=subprocess.run([tool("yt-dlp"),"--ignore-config","--no-plugin-dirs","--flat-playlist","--playlist-end",str(count),"--dump-single-json","--","https://www.youtube.com/@BlenderOfficial/"+suffix],capture_output=True,timeout=120,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            if result.returncode: raise SystemExit(result.stderr.decode("utf-8",errors="replace"))
            path.write_bytes(result.stdout)
    channel = json.loads((ROOT/"evidence-channel.json").read_text(encoding="utf-8-sig"))
    shorts = json.loads((ROOT/"evidence-shorts.json").read_text(encoding="utf-8-sig"))
    entries = [{"id":"aqz-KE-bpKQ"}] + [e | {"shorts":True} for e in shorts["entries"][:5]] + channel["entries"][:19]
    seen = set()
    entries = [e for e in entries if not(e["id"] in seen or seen.add(e["id"]))]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for item in pool.map(inspect,entries):
            results.append(item)
            print(item["id"],item["parse"],item.get("license",item.get("error",""))[:80],flush=True)
    report = {"utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"core_manifest":json.loads((ROOT/"tools/manifest.json").read_text()),
              "scope":"metadata only; no video data downloaded", "samples":results}
    (ROOT/"evidence/compatibility.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    eligible = [r for r in results if r.get("authorized_sample")]
    print("CC samples",len(eligible),"parsed",sum(r["parse"] for r in eligible),flush=True)
