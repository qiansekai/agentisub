# -*- coding: utf-8 -*-
"""analyze_unmatched.py — 未匹配块深度分析: 找最近邻歌词行 + 相似度, 输出分类建议。

输出 state/unmatched_analysis.json:
  [{song, id, ja, conf, best_line, ratio, verdict}]
  verdict: typo(疑似错字, ratio>=0.5) / loose(低相似, 可能live改词或版本差异)
"""
import difflib
import json
import re

def norm(s):
    s = str(s or "").replace("\u3000", " ")
    s = "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in s)
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    return s.lower()

blocks = []
for ln in open(r"D:\Kita-Tools\Media\agentisub\state\blocks.jsonl", encoding="utf-8"):
    ln = ln.strip()
    if ln:
        blocks.append(json.loads(ln))

lyrics = json.load(open(r"D:\Kita-Tools\Media\agentisub\state\lyrics.json", encoding="utf-8"))["songs"]
lyric_by_id = {s["id"]: s for s in lyrics}

out = []
for sid, lr in lyric_by_id.items():
    line_norms = [norm(x) for x in lr["lines"]]
    song_blocks = [b for b in blocks if b["kind"] == "lyric" and b["song"] == sid]
    for b in song_blocks:
        bn = norm(b["ja"])
        if not bn:
            continue
        if bn in line_norms:
            continue
        # 部分匹配（子串 70%）已在 check 脚本算过；这里找最近邻
        best_ratio = 0.0
        best_line = ""
        for i, ln in enumerate(line_norms):
            if not ln:
                continue
            r = difflib.SequenceMatcher(None, bn, ln).ratio()
            if r > best_ratio:
                best_ratio = r
                best_line = lr["lines"][i]
        if best_ratio >= 0.7:
            continue  # 已算 partial
        verdict = "typo" if best_ratio >= 0.5 else "loose"
        out.append({
            "song": sid,
            "id": b["id"],
            "ja": b["ja"],
            "conf": b["confidence"],
            "best_line": best_line,
            "ratio": round(best_ratio, 2),
            "verdict": verdict,
        })

out.sort(key=lambda x: -x["ratio"])
typo = [x for x in out if x["verdict"] == "typo"]
loose = [x for x in out if x["verdict"] == "loose"]
print("typo(疑似错字, 0.5<=r<0.7): %d" % len(typo))
for x in typo:
    print("  △ %s %s [%s] r=%.2f" % (x["id"], x["ja"][:36], x["conf"], x["ratio"]))
    print("      → 官方: %s" % x["best_line"][:60])
print("loose(live改词/版本差异, r<0.5): %d" % len(loose))
for x in loose:
    print("  ? %s %s [%s] r=%.2f → %s" % (x["id"], x["ja"][:36], x["conf"], x["ratio"], x["best_line"][:44]))

with open(r"D:\Kita-Tools\Media\agentisub\state\unmatched_analysis.json", "w", encoding="utf-8") as f:
    json.dump({"typo": typo, "loose": loose}, f, ensure_ascii=False, indent=1)
print("wrote state/unmatched_analysis.json")
