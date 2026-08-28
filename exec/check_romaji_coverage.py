# -*- coding: utf-8 -*-
"""check_romaji_coverage.py — 重抓网易云歌词接口, 统计每首官方罗马音(romalrc)覆盖行数。"""
import json
import re
import urllib.request

UA_HEADERS = {
    "Referer": "https://music.163.com",
    "User-Agent": "Mozilla/5.0",
    "Cookie": "appver=1.0.0; os=pc",
}

def fetch(nid):
    url = "https://music.163.com/api/song/lyric?id=%s&lv=1&tv=1&rv=1" % nid
    req = urllib.request.Request(url, headers=UA_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def count_lines(text):
    if not text:
        return 0
    n = 0
    for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]([^\[]*)", text):
        txt = m.group(4).strip()
        if txt and not re.match(r"^(作词|作曲|编曲|作詞|作曲|編曲|制作|製作)", txt):
            n += 1
    return n

lyrics = json.load(open(r"D:\Kita-Tools\Media\agentisub\state\lyrics.json", encoding="utf-8"))["songs"]
print("%-4s %-22s %6s %8s %8s" % ("曲", "标题", "原文行", "罗马音行", "缺失"))
missing = []
for s in lyrics:
    nid = s.get("netease_id")
    if not nid:
        print("%-4s %-22s (无网易云)" % (s["id"], s["title"][:20]))
        continue
    try:
        d = fetch(nid)
        ja_n = count_lines((d.get("lrc") or {}).get("lyric"))
        roma_n = count_lines((d.get("romalrc") or {}).get("lyric"))
        gap = ja_n - roma_n
        status = "❌" if roma_n == 0 else ("⚠️" if gap > 0 else "✅")
        print("%-4s %-22s %6d %8d %8d %s" % (s["id"], s["title"][:20], ja_n, roma_n, max(0, gap), status))
        if roma_n == 0:
            missing.append(s["id"])
    except Exception as e:
        print("%-4s %-22s ERR %s" % (s["id"], s["title"][:20], e))

print("\n完全无官方罗马音: %s" % (missing or "无"))
