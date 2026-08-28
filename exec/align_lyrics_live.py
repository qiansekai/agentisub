# -*- coding: utf-8 -*-
"""align_lyrics_live.py — 网易云歌词行对齐到 live 时间轴: LRC时间戳 -> DTW映射 -> live时间。

输出: state/lyrics_live.json
  {"songs":[{"id":"01","title":"...","lines":[{"ja","zh","roma","t"},...]}]}
t = live 时间(秒), 歌词行按 t 排序。当前播放行高亮/跳转都用这个。
"""
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

import numpy as np

ROOT = r"D:\Kita-Tools\Media\agentisub"
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"}

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

def fetch_lrc_cached(nid, sid):
    cache_dir = ROOT + r"\state\lrc"
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, "%s.json" % sid)
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    url = "https://music.163.com/api/song/lyric?id=%s&lv=1&tv=1&rv=1" % nid
    req = urllib.request.Request(url)
    req.add_header("Referer", "https://music.163.com")
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Cookie", "appver=1.0.0; os=pc")
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode("utf-8"))
    # 提取 lrc/tlyric/romalrc 时间戳行
    def ts_lines(text):
        out = []
        for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]([^\[]*)", text or ""):
            mm, ss, ms, txt = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4).strip()
            if txt and not re.match(r"^(作词|作曲|编曲|作詞|作曲|編曲|制作|製作)", txt):
                t = mm * 60 + ss + (int(ms.ljust(3, "0")) / 1000 if ms else 0)
                out.append((t, txt))
        return out
    lrc = ts_lines((d.get("lrc") or {}).get("lyric"))
    tly = ts_lines((d.get("tlyric") or {}).get("lyric"))
    roma = ts_lines((d.get("romalrc") or {}).get("lyric"))
    out = {"lrc": lrc, "tlyric": tly, "romalrc": roma}
    json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return out

def align_aux(ja_ts, aux_ts, tol=1.5):
    res = []
    for t, _ in ja_ts:
        best, bd = "", tol
        for t2, txt in aux_ts:
            d = abs(t2 - t)
            if d < bd:
                bd, best = d, txt
        res.append(best)
    return res

def main():
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    out = []
    for lyr in lyrics:
        sid = lyr["id"]
        # 映射
        amap = None
        for fname in ("%s.anchored.json", "%s.map.json"):
            p = os.path.join(ROOT, "state", "dtw", fname % sid)
            try:
                m = json.load(open(p, encoding="utf-8"))
                amap = (np.array(m["studio_t"]), np.array(m["live_t"]))
                break
            except Exception:
                continue
        if amap is None:
            print("%s | 无映射, 跳过" % sid)
            continue
        studio_arr, live_arr = amap
        raw = fetch_lrc_cached(lyr["netease_id"], sid)
        ja_ts = raw["lrc"]
        zh = align_aux(ja_ts, raw["tlyric"])
        # 罗马音优先用 lyrics.json 的 lines_roma(官方+站点抓取+pykakasi 兜底的合并结果), 回退官方 romalrc
        roma_local = dict(zip([norm(ln) for ln in lyr["lines"]],
                              lyr.get("lines_roma") or [""] * len(lyr["lines"])))
        roma_official = align_aux(ja_ts, raw["romalrc"])
        lines = []
        for i, (t, ja) in enumerate(ja_ts):
            live_t = float(np.interp(t, studio_arr, live_arr))
            r = roma_local.get(norm(ja)) or roma_official[i]
            lines.append({"ja": ja, "zh": zh[i], "roma": r, "t": round(live_t, 2)})
        lines.sort(key=lambda x: x["t"])
        out.append({"id": sid, "title": lyr["title"], "lines": lines})
        print("%s %s | %d 行对齐 (%.1f-%.1f)" % (sid, lyr["title"][:14], len(lines),
                                                  lines[0]["t"], lines[-1]["t"]))

    with open(ROOT + r"\state\lyrics_live.json", "w", encoding="utf-8") as f:
        json.dump({"songs": out}, f, ensure_ascii=False, indent=1)
    print("wrote state/lyrics_live.json: %d songs" % len(out))

if __name__ == "__main__":
    main()
