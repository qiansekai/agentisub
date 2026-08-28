# -*- coding: utf-8 -*-
"""gen_romaji.py — 用 pykakasi 给 lyrics.json 所有行生成罗马音(lines_roma)。"""
import json
import pykakasi

ROOT = r"D:\Kita-Tools\Media\agentisub"
data = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))

kakasi = pykakasi.kakasi()

total = 0
filled = 0
for s in data["songs"]:
    romas = list(s.get("lines_roma") or [""] * len(s.get("lines", [])))
    if len(romas) < len(s["lines"]):
        romas += [""] * (len(s["lines"]) - len(romas))
    for i, ln in enumerate(s.get("lines", [])):
        if romas[i]:
            continue
        try:
            segs = kakasi.convert(ln)
            r = " ".join(x["hepburn"] for x in segs if x.get("hepburn")).strip()
            romas[i] = r.lower()
            filled += 1
        except Exception:
            pass
        total += 1
    s["lines_roma"] = romas

with open(ROOT + r"\state\lyrics.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print("filled %d/%d missing romaji lines" % (filled, total))
