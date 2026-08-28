# -*- coding: utf-8 -*-
"""check_lyrics.py — agentisub 块 ja 文本 vs 网易云官方歌词 比对，输出不一致报告。

比对规则（宽松，容忍 live 改词）:
  norm: 去空白/去标点/全角转半角
  完全匹配: 块 norm == 某歌词行 norm
  部分匹配: 块 norm 与某歌词行 norm 互为子串(长度>=6 且占比>=70%)
  未匹配: 以上都不满足
"""
import json
import re

def norm(s):
    s = str(s or "")
    s = s.replace("　", " ").replace("\u3000", " ")
    # 全角字母数字转半角
    s = "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in s)
    # 去空白与标点
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    return s.lower()

blocks = json.load(open(r"D:\Kita-Tools\Media\agentisub\state\blocks.jsonl", encoding="utf-8")) if False else None
# blocks.jsonl 是 JSONL
blocks = []
for ln in open(r"D:\Kita-Tools\Media\agentisub\state\blocks.jsonl", encoding="utf-8"):
    ln = ln.strip()
    if ln:
        blocks.append(json.loads(ln))

lyrics = json.load(open(r"D:\Kita-Tools\Media\agentisub\state\lyrics.json", encoding="utf-8"))["songs"]
lyric_by_id = {s["id"]: s for s in lyrics}

report = []
for sid, lr in lyric_by_id.items():
    line_norms = [norm(x) for x in lr["lines"]]
    song_blocks = [b for b in blocks if b["kind"] == "lyric" and b["song"] == sid]
    matched = partial = unmatched = 0
    unmatched_list = []
    for b in song_blocks:
        bn = norm(b["ja"])
        if not bn:
            continue
        if bn in line_norms:
            matched += 1
            continue
        # 部分匹配：互为子串且占比>=70%
        best = 0.0
        for ln in line_norms:
            if not ln:
                continue
            if bn in ln or ln in bn:
                ratio = len(min(bn, ln, key=len)) / len(max(bn, ln, key=len))
                best = max(best, ratio)
        if best >= 0.7:
            partial += 1
        else:
            unmatched += 1
            unmatched_list.append({"id": b["id"], "ja": b["ja"], "conf": b["confidence"]})
    report.append({
        "song": sid,
        "title": lr["title"],
        "blocks": len(song_blocks),
        "matched": matched,
        "partial": partial,
        "unmatched": unmatched,
        "samples": unmatched_list[:5],
    })
    total = len(song_blocks)
    print("%s %s | 块=%d 完全=%d 部分=%d 未匹配=%d" % (sid, lr["title"], total, matched, partial, unmatched))
    for u in unmatched_list[:5]:
        print("     ✗ %s [%s] %s" % (u["id"], u["conf"], u["ja"][:50]))

with open(r"D:\Kita-Tools\Media\agentisub\state\lyric_check.json", "w", encoding="utf-8") as f:
    json.dump({"report": report}, f, ensure_ascii=False, indent=1)
print("wrote state/lyric_check.json")
