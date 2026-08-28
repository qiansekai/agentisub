# -*- coding: utf-8 -*-
"""dtw_verify.py — 用 DTW 映射校验 live 块时间轴: 块时间->studio 时间 与 LRC 官方时间戳对比。

对每首歌:
  1. 块文本 ↔ LRC 行文本 匹配(规范后)
  2. 块 live 时间经 DTW 映射 -> studio 时间
  3. 偏差 = |mapped - lrc_t|
汇总: 每首歌 平均偏差/中位偏差/最大偏差/匹配数 -> 时间轴健康度
输出: state/dtw/verify_report.json
"""
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

import numpy as np

ROOT = r"D:\Kita-Tools\Media\agentisub"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/"}

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

def fetch_lrc(nid):
    body = urllib.parse.urlencode({"id": nid, "lv": -1, "kv": -1, "tv": -1}).encode()
    req = urllib.request.Request("https://music.163.com/api/song/lyric", data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode("utf-8"))
    text = (d.get("lrc") or {}).get("lyric") or ""
    out = []
    for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]([^\[]*)", text):
        mm, ss, ms, txt = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4).strip()
        if txt and not re.match(r"^(作词|作曲|编曲|作詞|作曲|編曲|制作|製作)", txt):
            t = mm * 60 + ss + (int(ms.ljust(3, "0")) / 1000 if ms else 0)
            out.append((t, txt))
    return out

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return blocks

def main():
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    blocks = load_blocks()
    report = []

    for lyr in lyrics:
        sid = lyr["id"]
        try:
            m = json.load(open(ROOT + r"\state\dtw\%s.map.json" % sid, encoding="utf-8"))
        except Exception:
            continue
        live_t = np.array(m["live_t"])
        studio_t = np.array(m["studio_t"])
        lrc = fetch_lrc(lyr["netease_id"])
        lrc_norm = [(t, txt, norm(txt)) for t, txt in lrc if norm(txt)]

        song_blocks = [b for b in blocks if b["kind"] == "lyric" and b["song"] == sid]
        matched = 0
        devs = []
        for b in song_blocks:
            bn = norm(b["ja"])
            if not bn:
                continue
            hit = None
            for t, txt, ln in lrc_norm:
                if bn == ln or (len(bn) >= 4 and (bn in ln or ln in bn)):
                    hit = t
                    break
            if hit is None:
                continue
            mapped = float(np.interp(b["start"], live_t, studio_t))
            dev = abs(mapped - hit)
            devs.append(dev)
            matched += 1

        if devs:
            devs = np.array(devs)
            report.append({
                "song": sid, "title": lyr["title"], "matched": matched,
                "mean_dev": round(float(devs.mean()), 2),
                "median_dev": round(float(np.median(devs)), 2),
                "max_dev": round(float(devs.max()), 2),
                "bad_blocks": int((devs > 3.0).sum()),
            })
            print("%s %-22s | 匹配=%2d/%2d | 平均偏差=%.2fs 中位=%.2fs 最大=%.2fs | >3s异常块=%d" % (
                sid, lyr["title"][:20], matched, len(song_blocks),
                devs.mean(), np.median(devs), devs.max(), (devs > 3.0).sum()))
        else:
            print("%s %-22s | 无文本匹配" % (sid, lyr["title"][:20]))

    with open(ROOT + r"\state\dtw\verify_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\nwrote state/dtw/verify_report.json")

if __name__ == "__main__":
    main()
