# -*- coding: utf-8 -*-
"""fix_damaged.py — 批量修复压缩损坏曲: align_song prompt 整曲对齐 -> rebuild 重建。

损坏曲清单(diagnose 压缩>=2): 05(1) 07 08 11 12 13 17 18 20
流程每曲:
  1. align_song.py prompt 模式 -> aligned JSON (live 实际演唱顺序的对齐)
  2. rebuild: piapro 行+aligned时间+插值 -> 新块预览
  3. 汇总重建前后统计
用法: python fix_damaged.py [--apply]
"""
import json
import os
import re
import subprocess
import sys
import unicodedata

ROOT = r"D:\Kita-Tools\Media\agentisub"
ANIMA3 = r"D:\Kita-Tools\Media\Anima3"
PY = ANIMA3 + r"\.venv\Scripts\python.exe"
WAV = ANIMA3 + r"\anima3_16k.wav"

# 压缩损坏曲(按诊断)
DAMAGED = ["05", "07", "08", "11", "12", "13", "17", "18", "20"]

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

def read_piapro(sid):
    lines, in_body = [], False
    with open(ANIMA3 + r"\lyrics\%s.txt" % sid, encoding="utf-8") as f:
        for raw in f:
            s = raw.rstrip("\n").rstrip("\r")
            if not in_body:
                if s.strip() == "---":
                    in_body = True
                continue
            s = s.strip()
            if s:
                lines.append(s)
    return lines

def run_align(sid):
    songs = json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]
    sm = next(s for s in songs if s["id"] == sid)
    out_dir = ROOT + r"\state\retime_tmp"
    os.makedirs(out_dir, exist_ok=True)
    ltxt = ANIMA3 + r"\lyrics\%s.txt" % sid
    if not os.path.exists(ltxt):
        print("  missing lyrics txt, skip")
        return None
    cmd = [PY, ANIMA3 + r"\align_song.py", ltxt, "--mode", "prompt", "--audio", WAV,
           "--t0", str(sm["t0"]), "--t1", str(sm["t1"]), "--device", "cpu", "--compute", "int8",
           "--outdir", out_dir, "--song-id", sid]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    tail = (r.stdout or "")[-300:]
    print("  align: %s" % tail.replace("\n", " | ")[-200:])
    if r.returncode != 0:
        print("  align FAILED")
        return None
    apath = out_dir + "\\%s.aligned.json" % sid
    try:
        return json.load(open(apath, encoding="utf-8"))
    except Exception:
        return None

def rebuild(sid, aligned, apply):
    piapro = read_piapro(sid)
    aligned_by_norm = {norm(a["line"]): a for a in aligned}
    times = []
    for ln in piapro:
        a = aligned_by_norm.get(norm(ln))
        times.append((a["start"], a["end"]) if a else None)
    # 插值
    for i, t in enumerate(times):
        if t is not None:
            continue
        lo = hi = None
        for j in range(i - 1, -1, -1):
            if times[j] is not None:
                lo = j
                break
        for j in range(i + 1, len(times)):
            if times[j] is not None:
                hi = j
                break
        if lo is not None and hi is not None:
            s = times[lo][1] + (times[hi][0] - times[lo][1]) * (i - lo) / (hi - lo)
            times[i] = (round(s, 2), round(s + 1.5, 2))
        elif lo is not None:
            s = times[lo][1] + 2.0 * (i - lo)
            times[i] = (round(s, 2), round(s + 1.5, 2))
        elif hi is not None:
            s = times[hi][0] - 2.0 * (hi - i)
            times[i] = (round(s, 2), round(s + 1.5, 2))
    n_aligned = sum(1 for ln in piapro if norm(ln) in aligned_by_norm)
    # 旧块 zh/tags 迁移
    old = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            old.append(json.loads(ln))
    old_by_norm = {}
    for b in old:
        if b["kind"] == "lyric" and b["song"] == sid:
            n = norm(b["ja"])
            if n and n not in old_by_norm:
                old_by_norm[n] = b
    new_blocks = []
    for i, ln in enumerate(piapro):
        st, en = times[i]
        ob = old_by_norm.get(norm(ln))
        new_blocks.append({
            "id": "%s-%03d" % (sid, i + 1), "start": st, "end": en,
            "kind": "lyric", "song": sid, "ja": ln, "zh": ob["zh"] if ob else "",
            "confidence": ob["confidence"] if ob else "green",
            "evidence": {"method": "rebuild_aligned", "detail": "压缩损坏重建"},
            "tags": ob["tags"] if ob else [],
            "history": [{"actor": "rebuild", "ts": "2026-08-29T00:00:00+08:00",
                         "note": "时间压缩损坏重建"}],
            "locked": False,
        })
    print("  piapro %d 行, aligned %d, 插值 %d -> 新块 %d (旧 %d)" % (
        len(piapro), n_aligned, len(piapro) - n_aligned, len(new_blocks),
        sum(1 for b in old if b["kind"] == "lyric" and b["song"] == sid)))
    if apply:
        other = [b for b in old if not (b["kind"] == "lyric" and b["song"] == sid)]
        merged = other + new_blocks
        merged.sort(key=lambda b: b["start"])
        with open(ROOT + r"\state\blocks.jsonl", "w", encoding="utf-8") as f:
            for b in merged:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
        print("  WRITTEN")
    return len(new_blocks)

def main():
    apply = "--apply" in sys.argv
    for sid in DAMAGED:
        print("=" * 56)
        print("SONG %s" % sid)
        aligned = run_align(sid)
        if aligned is None:
            continue
        rebuild(sid, aligned, apply)
    if apply:
        print("\nblocks.jsonl 已重建, 需重启服务加载")
    else:
        print("\n预览模式: 加 --apply 写入")

if __name__ == "__main__":
    main()
