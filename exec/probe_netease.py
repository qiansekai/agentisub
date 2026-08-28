# -*- coding: utf-8 -*-
"""批量在网易云搜索 agentisub 曲目列表，输出匹配候选（不抓歌词，只摸底）。"""
import json
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/", "Content-Type": "application/x-www-form-urlencoded"}

def get(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def search(q, limit=6):
    return get("https://music.163.com/api/search/get", {"s": q, "type": 1, "limit": limit, "offset": 0})

songs = json.load(open(r"D:\Kita-Tools\Media\agentisub\state\songs.json", encoding="utf-8"))["songs"]

for s in songs:
    q = "ヰ世界情緒 " + s["title"].split("（")[0].split("/")[0].strip()
    try:
        res = search(q)
        items = (res.get("result") or {}).get("songs") or []
        # 过滤：优先 exact 同名 + 歌手含 ヰ世界情緒；排除 covered by
        cand = []
        for it in items:
            name = it["name"]
            artists = "/".join(a["name"] for a in it.get("artists", []))
            album = (it.get("album") or {}).get("name", "")
            if "covered" in name.lower():
                continue
            ok = s["title"].split("（")[0].split("/")[0].strip() in name or name in s["title"]
            cand.append({"id": it["id"], "name": name, "artists": artists, "album": album, "exact": ok})
        best = cand[0] if cand else None
        print("%s | %s | -> %s" % (s["id"], s["title"], json.dumps(best, ensure_ascii=False) if best else "NO_MATCH"))
    except Exception as e:
        print("%s | %s | -> ERR %s" % (s["id"], s["title"], e))
