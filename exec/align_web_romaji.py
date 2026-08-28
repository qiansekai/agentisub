# -*- coding: utf-8 -*-
"""align_web_romaji.py — 站点罗马音(web_romaji.json)对齐到网易云歌词行, 写入 lyrics.json。

对齐: 站点行按读音指纹累积拼接, 匹配网易云歌词行的读音(pykakasi), 贪心双指针。
"""
import json
import re
import unicodedata

import pykakasi

ROOT = r"D:\Kita-Tools\Media\agentisub"

kakasi = pykakasi.kakasi()

def finger_ja(ja):
    """歌词行 -> 读音指纹(小写无空格)"""
    try:
        segs = kakasi.convert(ja)
        return "".join(x["hepburn"] for x in segs if x.get("hepburn")).lower()
    except Exception:
        return ""

def finger_roma(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())

def main():
    web = json.load(open(ROOT + r"\exec\web_romaji.json", encoding="utf-8"))
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))
    by_id = {s["id"]: s for s in lyrics["songs"]}

    for sid, w in web.items():
        song = by_id.get(sid)
        if not song:
            print("%s: 无歌词数据" % sid)
            continue
        site_lines = [l for l in w["lines"] if l.strip()]
        ja_lines = song["lines"]
        out = [""] * len(ja_lines)
        # 行数一致 -> 直接按序一一对应(站点行序=歌词行序, 读法差异不影响)
        if len(site_lines) == len(ja_lines):
            out = site_lines[:]
            matched = len(out)
        else:
            # 行数不一致 -> 窗口贪心匹配(容忍增删行), 失败行留空
            import difflib
            si = 0
            matched = 0
            for i, ja in enumerate(ja_lines):
                target = finger_ja(ja)
                if not target:
                    continue
                best_j, best_ratio = -1, 0.62
                for j in range(si, min(si + 5, len(site_lines))):
                    r = difflib.SequenceMatcher(None, target, finger_roma(site_lines[j])).ratio()
                    if r > best_ratio:
                        best_j, best_ratio = j, r
                if best_j >= 0:
                    out[i] = site_lines[best_j]
                    si = best_j + 1
                    matched += 1
        n_filled = sum(1 for x in out if x)
        # 写入: 官方罗马音优先, 站点罗马音填补空行
        romas = list(song.get("lines_roma") or [""] * len(ja_lines))
        if len(romas) < len(ja_lines):
            romas += [""] * (len(ja_lines) - len(romas))
        for i in range(len(ja_lines)):
            if out[i]:
                romas[i] = out[i]
        song["lines_roma"] = romas
        print("%s | %s | 站点行 %d -> 歌词行 %d, 对齐 %d, 填补 %d" % (
            sid, song["title"][:16], len(site_lines), len(ja_lines), matched, n_filled))

    with open(ROOT + r"\state\lyrics.json", "w", encoding="utf-8") as f:
        json.dump(lyrics, f, ensure_ascii=False, indent=1)
    print("lyrics.json updated")

if __name__ == "__main__":
    main()
