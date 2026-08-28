# -*- coding: utf-8 -*-
"""probe_all_audio.py — 批量试下载 19 首网易云录音室音频, 检查 VIP 试听限制。

输出: 每首 下载字节数 + ffprobe 时长 vs 网易云元数据时长(搜索接口 duration) -> 全曲/试听/失败
"""
import json
import os
import subprocess
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/"}
ROOT = r"D:\Kita-Tools\Media\agentisub"
OUT_DIR = ROOT + r"\state\dtw"
os.makedirs(OUT_DIR, exist_ok=True)

def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def duration(path):
    r = subprocess.run([ffmpeg(), "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    import re
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None

def fetch_duration_meta(nid):
    """搜索接口元数据里的时长(毫秒)。用 song/detail API。"""
    try:
        import urllib.parse
        url = "https://music.163.com/api/song/detail?ids=[%s]" % nid
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        s = (d.get("songs") or [None])[0]
        if s and s.get("duration"):
            return s["duration"] / 1000.0
    except Exception as e:
        print("  meta err: %s" % e)
    return None

def main():
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    print("共 %d 首" % len(lyrics))
    results = []
    for s in lyrics:
        nid = s["netease_id"]
        mp3 = os.path.join(OUT_DIR, "%s.mp3" % s["id"])
        try:
            u = "https://music.163.com/song/media/outer/url?id=%s.mp3" % nid
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            open(mp3, "wb").write(data)
            dur = duration(mp3)
            meta_dur = fetch_duration_meta(nid)
            status = "?"
            if dur is None:
                status = "BAD(非音频)"
            elif meta_dur and dur < meta_dur * 0.7:
                status = "试听片段"
            elif dur and dur < 60:
                status = "试听片段(<60s)"
            else:
                status = "全曲"
            print("%s %s | %d bytes | dur=%.1fs | meta=%.1fs | %s" % (
                s["id"], s["title"][:18], len(data), dur or 0, meta_dur or 0, status))
            results.append((s["id"], status))
        except Exception as e:
            print("%s %s | ERR %s" % (s["id"], s["title"][:18], e))
            results.append((s["id"], "ERR"))
    print("\n汇总:")
    from collections import Counter
    print(Counter(r[1] for r in results))

if __name__ == "__main__":
    main()
