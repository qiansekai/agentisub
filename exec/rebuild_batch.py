# rebuild_batch.py — 批量跑 rebuild_live(预览存JSON) 9 首损坏曲
import json
import os
import subprocess

ROOT = r"D:\Kita-Tools\Media\agentisub"
PY = r"D:\Kita-Tools\Media\Anima3\.venv\Scripts\python.exe"
SCRIPT = ROOT + r"\exec\rebuild_live.py"
OUT_DIR = ROOT + r"\state\rebuild"
os.makedirs(OUT_DIR, exist_ok=True)

DAMAGED = ["05", "07", "08", "11", "12", "13", "17", "18", "20"]

for sid in DAMAGED:
    print("=" * 56, flush=True)
    print("SONG %s" % sid, flush=True)
    out = os.path.join(OUT_DIR, "%s.json" % sid)
    r = subprocess.run([PY, SCRIPT, "--song", sid, "--out", out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1200)
    tail = (r.stdout or "")[-700:]
    print(tail, flush=True)
    if r.returncode != 0:
        print("FAILED: %s" % (r.stderr or "")[-300:], flush=True)

print("done")
