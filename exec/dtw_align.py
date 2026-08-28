# -*- coding: utf-8 -*-
"""dtw_align.py — 网易云录音室版 ↔ live 音频 DTW 对齐（M4 复活: 用正常版音乐补上"录音室参考音源"）。

用法:
  python dtw_align.py --song 05                 # 下载 studio mp3 + DTW 对齐 + 输出映射
  python dtw_align.py --song 05 --compare       # 用映射把 live 块时间换算到 studio 时间, 与 LRC 时间戳对比

原理(规划十四节学术方案): chroma + DTW 现场歌词同步。live 演出 vs 录音室版有全局变速/插段,
用 DTW 得到 live_t <-> studio_t 映射, 进而: 1) 校验 live 块时间轴 2) 为 DTW 曲线图层供数据。
输出: state/dtw/<song>.map.json  {live_t:[...], studio_t:[...]}  + 报告
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import wave

import numpy as np

ROOT = r"D:\Kita-Tools\Media\agentisub"
WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/"}

def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def load_songs():
    return json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]

def load_lyrics():
    d = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))
    return {s["id"]: s for s in d["songs"]}

def download_mp3(nid, out):
    if os.path.exists(out) and os.path.getsize(out) > 100000:
        print("reuse cached: %s" % out)
        return
    u = "https://music.163.com/song/media/outer/url?id=%s.mp3" % nid
    req = urllib.request.Request(u, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    open(out, "wb").write(data)
    print("downloaded %d bytes -> %s" % (len(data), out))

def to_16k(src, dst):
    subprocess.run([ffmpeg(), "-y", "-i", src, "-ar", "16000", "-ac", "1", dst],
                   capture_output=True, check=True)
    print("converted -> %s" % dst)

def read_wav(path, t0=0.0, t1=None):
    w = wave.open(path, "rb")
    sr = w.getframerate()
    if t1 is None:
        t1 = w.getnframes() / sr
    w.setpos(int(t0 * sr))
    n = int((t1 - t0) * sr)
    data = w.readframes(n)
    w.close()
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0, sr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()

    songs = load_songs()
    smeta = next((s for s in songs if s["id"] == args.song), None)
    if not smeta:
        print("song not found: %s" % args.song)
        sys.exit(1)
    lyr = load_lyrics().get(args.song)
    if not lyr:
        print("song %s 无网易云收录(Capullo 等), 无法 DTW" % args.song)
        sys.exit(2)

    os.makedirs(ROOT + r"\state\dtw", exist_ok=True)
    mp3 = ROOT + r"\state\dtw\%s.mp3" % args.song
    wav16 = ROOT + r"\state\dtw\%s_studio.wav" % args.song

    print("== download studio audio (%s) ==" % lyr["title"])
    download_mp3(lyr["netease_id"], mp3)
    to_16k(mp3, wav16)

    import librosa
    print("== load audio ==")
    live_audio, _ = read_wav(WAV, smeta["t0"], smeta["t1"])
    studio_audio, _ = read_wav(wav16)

    print("== chroma ==")
    hop = 4096
    c_live = librosa.feature.chroma_cqt(y=live_audio, sr=16000, hop_length=hop)
    c_studio = librosa.feature.chroma_cqt(y=studio_audio, sr=16000, hop_length=hop)
    print("chroma shapes: live=%s studio=%s" % (c_live.shape, c_studio.shape))

    print("== DTW (Sakoe-Chiba band) ==")
    D, wp = librosa.sequence.dtw(X=c_live, Y=c_studio, metric="cosine",
                                 global_constraints=True, band_rad=0.1)
    live_idx, studio_idx = wp[:, 0], wp[:, 1]
    live_t = smeta["t0"] + live_idx * (hop / 16000.0)
    studio_t = studio_idx * (hop / 16000.0)
    # 确保升序（librosa 路径顺序保证升序，但稳妥起见显式排序）
    order = np.argsort(live_t)
    live_t = live_t[order]
    studio_t = studio_t[order]

    # 采样映射(等距降采样到 200 点存文件)
    step = max(1, len(live_t) // 200)
    sample = list(range(0, len(live_t), step)) + [len(live_t) - 1]
    out = {"song": args.song, "title": lyr["title"],
           "live_t": [round(float(live_t[i]), 2) for i in sample],
           "studio_t": [round(float(studio_t[i]), 2) for i in sample],
           "cost": round(float(D[-1, -1]), 2)}
    with open(ROOT + r"\state\dtw\%s.map.json" % args.song, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("map saved: %d points, cost=%.2f" % (len(sample), out["cost"]))

    # 报告映射概况
    print("live %.1f-%.1f <-> studio %.1f-%.1f" % (live_t[0], live_t[-1], studio_t[0], studio_t[-1]))

    if args.compare:
        # 把 live 块时间映射到 studio 时间, 与网易云 LRC 时间戳对比
        lrc = fetch_lrc_timestamps(lyr["netease_id"])
        blocks = [b for b in load_blocks() if b["kind"] == "lyric" and b["song"] == args.song]
        mapped = np.interp([b["start"] for b in blocks], live_t, studio_t)
        # 报告前 10 块
        for b, m in list(zip(blocks, mapped))[:10]:
            print("%s live %.1f -> studio %.1f" % (b["id"], b["start"], m))
        if lrc:
            print("LRC timestamps sample: %s" % lrc[:5])

def fetch_lrc_timestamps(nid):
    """抓原始 LRC 并解析 [mm:ss.xx] 时间戳行 -> [(t, text)]"""
    import urllib.parse
    body = urllib.parse.urlencode({"id": nid, "lv": -1, "kv": -1, "tv": -1}).encode()
    req = urllib.request.Request("https://music.163.com/api/song/lyric", data=body, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode("utf-8"))
    text = (d.get("lrc") or {}).get("lyric") or ""
    out = []
    for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]([^\[]*)", text):
        mm, ss, ms, txt = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4).strip()
        if txt:
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

if __name__ == "__main__":
    main()
