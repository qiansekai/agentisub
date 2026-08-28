# autotime_batch.py — 批量自主打轴: 全部有映射的曲跑 autotime --apply
import json
import subprocess

ROOT = r"D:\Kita-Tools\Media\agentisub"
PY = r"D:\Kita-Tools\Media\Anima3\.venv\Scripts\python.exe"
SCRIPT = ROOT + r"\exec\autotime.py"

lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
song_ids = [s["id"] for s in lyrics]

total = 0
for sid in song_ids:
    r = subprocess.run([PY, SCRIPT, "--song", sid, "--apply"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    out = (r.stdout or "").strip()
    print("%s | %s" % (sid, out.replace("\n", " | ")[-160:]), flush=True)
    if "applied" in out:
        import re
        m = re.search(r"applied\":\s*(\d+)", out)
        if m:
            total += int(m.group(1))
print("\nTOTAL applied: %d" % total)
