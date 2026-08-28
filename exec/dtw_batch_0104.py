# dtw_batch_0104.py — 01-04 曲 DTW 对齐
import subprocess

PY = r"D:\Kita-Tools\Media\Anima3\.venv\Scripts\python.exe"
DTW = r"D:\Kita-Tools\Media\agentisub\exec\dtw_align.py"

for sid in ["01", "02", "03", "04"]:
    print("=" * 50, flush=True)
    print("SONG %s" % sid, flush=True)
    r = subprocess.run([PY, DTW, "--song", sid], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1200)
    tail = (r.stdout or "")[-400:]
    print(tail, flush=True)
print("done")
