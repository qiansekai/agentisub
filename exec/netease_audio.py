# -*- coding: utf-8 -*-
"""netease_audio.py — 网易云歌曲音频 URL 探测（POC: 验证能否拿到录音室版音频用于 DTW）。

用法: python netease_audio.py <song_id> [out.mp3]
"""
import json
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/"}

def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def main():
    song_id = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    cookie = sys.argv[3] if len(sys.argv) > 3 else ""

    # 方式1: song/enhance/player/url (POST form, 可带 Cookie)
    import urllib.parse
    body = urllib.parse.urlencode({"ids": "[%s]" % song_id, "br": 128000}).encode()
    headers = dict(UA)
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request("https://music.163.com/api/song/enhance/player/url",
                                 data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        songs = data.get("data") or []
        if songs and songs[0].get("url"):
            url = songs[0]["url"]
            print("player/url OK: %s" % url[:100])
            if out:
                audio = get(url)
                open(out, "wb").write(audio)
                print("downloaded %d bytes -> %s" % (len(audio), out))
            return
        print("player/url returned no url: %s" % json.dumps(data, ensure_ascii=False)[:200])
    except Exception as e:
        print("player/url ERR: %s" % e)

    # 方式2: song/media/outer/url (GET 直接 mp3)
    for fmt in ("mp3", "m4a"):
        try:
            u = "https://music.163.com/song/media/outer/url?id=%s.%s" % (song_id, fmt)
            audio = get(u)
            if len(audio) > 10000 and not audio[:2] == b'{"':
                print("outer/url OK (%s): %d bytes" % (fmt, len(audio)))
                if out:
                    open(out, "wb").write(audio)
                    print("downloaded -> %s" % out)
                return
            print("outer/url %s: %s" % (fmt, audio[:80]))
        except Exception as e:
            print("outer/url %s ERR: %s" % (fmt, e))

if __name__ == "__main__":
    main()
