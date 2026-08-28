# -*- coding: utf-8 -*-
"""retime.py — M2 轴不准标记修复: 曲级别歌词提示 ASR 重对齐 → 该曲所有块 patches。

用法:
  python retime.py --song 07                 # 重对齐整曲, 打印 patches(块→新时间轴)
  python retime.py --song 07 --apply         # 直接 POST /api/patches 回写

原理: 唱歌段裸 ASR 词级时间戳不可靠; 正确做法是整曲歌词作 initial_prompt 的
      prompt-mode 转录(Anima3 管线已验证), 逐行得到可靠时间轴, 再按文本匹配到块。
      无官方歌词的曲(Capullo)无法重对齐, 如实退出。
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
import urllib.request

ROOT = r"D:\Kita-Tools\Media\agentisub"
ANIMA3 = r"D:\Kita-Tools\Media\Anima3"
PY = ANIMA3 + r"\.venv\Scripts\python.exe"
API = "http://127.0.0.1:8720"

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※]", "", s)
    return s

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return blocks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    lyr = next((s for s in lyrics if s["id"] == args.song), None)
    if not lyr:
        print("song %s 无官方歌词(Capullo 无收录), 无法重对齐" % args.song)
        sys.exit(2)

    blocks = [b for b in load_blocks() if b["kind"] == "lyric" and b["song"] == args.song]
    print("song %s: %d 块, %d 歌词行" % (args.song, len(blocks), len(lyr["lines"])))

    # 歌曲时间范围
    songs = json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]
    smeta = next((s for s in songs if s["id"] == args.song), None)
    if not smeta:
        print("song %s not in songs.json" % args.song)
        sys.exit(1)
    t0, t1 = smeta["t0"], smeta["t1"]

    # 1. 调 Anima3 align_song.py 的 prompt 模式整曲对齐
    out_dir = ROOT + r"\state\retime_tmp"
    import os
    os.makedirs(out_dir, exist_ok=True)
    lyrics_txt = ANIMA3 + r"\lyrics\%s.txt" % args.song
    if not os.path.exists(lyrics_txt):
        print("missing lyrics txt: %s" % lyrics_txt)
        sys.exit(1)
    cmd = [PY, ANIMA3 + r"\align_song.py", lyrics_txt,
           "--mode", "prompt", "--audio", ANIMA3 + r"\anima3_16k.wav",
           "--t0", str(t0), "--t1", str(t1),
           "--device", "cpu", "--compute", "int8",
           "--outdir", out_dir, "--song-id", args.song]
    print("running: " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=900)
    print(r.stdout[-800:] if r.stdout else "")
    if r.returncode != 0:
        print("align failed: " + (r.stderr or "")[-500:])
        sys.exit(1)

    # 2. 读 aligned 结果
    aligned_path = out_dir + "\\" + args.song + ".aligned.json"
    try:
        aligned = json.load(open(aligned_path, encoding="utf-8"))
    except Exception as e:
        print("read aligned failed: %s" % e)
        sys.exit(1)
    print("aligned lines: %d" % len(aligned))

    # 3. 文本匹配: 块 ja -> aligned 行 (行可能有重复, 按出现顺序消费)
    used = [False] * len(aligned)
    patches = []
    matched = 0
    for b in blocks:
        bn = norm(b["ja"])
        hit = None
        for i, a in enumerate(aligned):
            if used[i]:
                continue
            an = norm(a["line"])
            if bn and an and (bn == an or bn in an or an in bn):
                hit = i
                used[i] = True
                break
        if hit is None:
            continue
        a = aligned[hit]
        if abs(a["start"] - b["start"]) > 0.3 or abs(a["end"] - b["end"]) > 0.3:
            patches.append({
                "id": "P-RETIME-%s" % b["id"],
                "block_id": b["id"],
                "tag_id": "",
                "reply": "歌词提示ASR曲级重对齐: 原 [%.2f-%.2f] -> 新 [%.2f-%.2f]" % (
                    b["start"], b["end"], a["start"], a["end"]),
                "changes": {"start": round(a["start"], 2), "end": round(a["end"], 2)},
            })
            print("  %s: %.2f-%.2f -> %.2f-%.2f" % (b["id"], b["start"], b["end"], a["start"], a["end"]))
            matched += 1
    print("matched %d/%d blocks, %d need retime" % (matched, len(blocks), len(patches)))

    if patches and args.apply:
        req = urllib.request.Request(API + "/api/patches", data=json.dumps(patches).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            print("applied: " + resp.read().decode())
    elif patches:
        with open(ROOT + r"\state\retime_patches.json", "w", encoding="utf-8") as f:
            json.dump(patches, f, ensure_ascii=False, indent=1)
        print("wrote state/retime_patches.json (用 --apply 回写)")

if __name__ == "__main__":
    main()
