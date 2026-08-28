# -*- coding: utf-8 -*-
"""check_block_times.py — 歌词行(live映射时间) vs 匹配块时间 偏差检查。"""
import json
import re
import unicodedata

ROOT = r"D:\Kita-Tools\Media\agentisub"

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

blocks = []
for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
    ln = ln.strip()
    if ln:
        blocks.append(json.loads(ln))

ll = json.load(open(ROOT + r"\state\lyrics_live.json", encoding="utf-8"))["songs"]
ll_by_id = {s["id"]: s for s in ll}

for sid, song in ll_by_id.items():
    blks = [b for b in blocks if b["kind"] == "lyric" and b["song"] == sid]
    bnorms = {norm(b["ja"]): b for b in blks}
    devs = []
    missing = 0
    for line in song["lines"]:
        n = norm(line["ja"])
        b = bnorms.get(n)
        if b is None:
            missing += 1
            continue
        devs.append(abs(b["start"] - line["t"]))
    if devs:
        devs.sort()
        med = devs[len(devs) // 2]
        print("%-4s 行=%d 块=%d 缺失=%d 中位偏差=%.1fs 最大=%.1fs >3s=%d" % (
            sid, len(song["lines"]), len(blks), missing, med, devs[-1], sum(1 for d in devs if d > 3)))
    else:
        print("%-4s 行=%d 块=%d 缺失=%d (无匹配)" % (sid, len(song["lines"]), len(blks), missing))
