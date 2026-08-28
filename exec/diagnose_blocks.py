# -*- coding: utf-8 -*-
"""diagnose_blocks.py — 全量扫描块数据质量: 找迁移 bug 指纹(同文本重复块 + 同时间压缩块)。

指纹:
  1. 重复: 同曲内 norm(ja) 相同的块 >=2 个
  2. 压缩: 同曲内 start 完全相同的块 >=2 个(或 相邻块间距 < 0.5s 的密集簇)
输出: 每曲诊断 + 损坏曲清单
"""
import json
import re
import unicodedata

ROOT = r"D:\Kita-Tools\Media\agentisub"

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return blocks

def main():
    blocks = load_blocks()
    songs = sorted(set(b["song"] for b in blocks if b["kind"] == "lyric" and b["song"]))
    print("%-6s %-26s %6s %6s %6s" % ("曲", "标题", "块数", "重复", "压缩"))
    damaged = []
    titles = {}
    try:
        for s in json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]:
            titles[s["id"]] = s["title"]
    except Exception:
        pass

    for sid in songs:
        bs = [b for b in blocks if b["kind"] == "lyric" and b["song"] == sid]
        # 重复: 同 norm 出现 >=2 次
        seen = {}
        dup = 0
        for b in bs:
            n = norm(b["ja"])
            if n:
                seen[n] = seen.get(n, 0) + 1
        dup = sum(v - 1 for v in seen.values() if v > 1)
        # 压缩: 同 start 块数 >=2
        starts = {}
        for b in bs:
            key = round(b["start"], 1)
            starts[key] = starts.get(key, 0) + 1
        squeeze = sum(v - 1 for v in starts.values() if v > 1)
        status = ""
        if dup >= 3 or squeeze >= 3:
            damaged.append((sid, dup, squeeze))
            status = " <<< 损坏"
        print("%-6s %-26s %6d %6d %6d%s" % (sid, (titles.get(sid) or "")[:24], len(bs), dup, squeeze, status))

    print("\n损坏曲清单: %s" % ([(s, d, q) for s, d, q in damaged] if damaged else "无"))

if __name__ == "__main__":
    main()
