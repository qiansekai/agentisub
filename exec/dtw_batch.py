# dtw_batch.py — 批量跑 19 首 DTW 对齐, 汇总映射结果
import json
import os
import subprocess
import sys

ROOT = r"D:\Kita-Tools\Media\agentisub"
PY = r"D:\Kita-Tools\Media\Anima3\.venv\Scripts\python.exe"
DTW = ROOT + r"\exec\dtw_align.py"

lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
song_ids = [s["id"] for s in lyrics]

results = []
for sid in song_ids:
    print("=" * 50)
    print("SONG %s" % sid, flush=True)
    r = subprocess.run([PY, DTW, "--song", sid], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1200)
    tail = (r.stdout or "")[-600:]
    print(tail, flush=True)
    ok = r.returncode == 0 and ("map saved" in (r.stdout or ""))
    results.append({"song": sid, "ok": ok})
    map_path = ROOT + r"\state\dtw\%s.map.json" % sid
    if os.path.exists(map_path):
        try:
            m = json.load(open(map_path, encoding="utf-8"))
            results[-1]["cost"] = m.get("cost")
            results[-1]["points"] = len(m.get("live_t", []))
        except Exception:
            pass

print("\n" + "=" * 50)
print("SUMMARY")
for x in results:
    print("%s %s cost=%s" % (x["song"], "OK " if x["ok"] else "FAIL", x.get("cost", "?")))
with open(ROOT + r"\state\dtw\batch_summary.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
