# -*- coding: utf-8 -*-
"""dtw_vocal.py — demucs 人声分离 + 人声锚点 DTW（升级整轨和声对齐为人声对齐）。

用法: python dtw_vocal.py --song 08
流程: demucs(htdemucs) 分离 live 段与 studio 版人声 -> 人声 chroma -> 锚点分段 DTW -> 偏差对比
输出: state/dtw/{song}.vocal.anchored.json + 整轨vs人声 偏差对比
"""
import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import wave

import numpy as np

ROOT = r"D:\Kita-Tools\Media\agentisub"
WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"}

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

def read_wav_seg(path, t0, t1):
    w = wave.open(path, "rb")
    sr = w.getframerate()
    w.setpos(int(t0 * sr))
    n = int((t1 - t0) * sr)
    data = w.readframes(n)
    w.close()
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

def separate_vocals(audio_16k, tag):
    """demucs 分离, 返回人声(16k mono numpy)。CPU 推理, 缓存到 npy。"""
    import os
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    cache = ROOT + r"\state\dtw\_voc_%s.npy" % tag
    if os.path.exists(cache):
        return np.load(cache)

    model = get_model("htdemucs")
    # mono 16k -> 立体声 44.1k（demucs 要求 2 通道 44100Hz）
    n44 = int(len(audio_16k) * 44100 / 16000)
    idx = np.linspace(0, len(audio_16k) - 1, n44).astype(int)
    x44 = torch.from_numpy(audio_16k[idx].astype(np.float32))
    stereo = torch.stack([x44, x44], dim=0)[None]  # (1, 2, n)
    with torch.no_grad():
        stems = apply_model(model, stereo, device="cpu", split=True, overlap=0.25)
    # stems: (batch, sources, channels, samples) at 44.1kHz
    vocals = stems[0, 3].mean(dim=0).numpy()  # source 3 = vocals, mono 平均
    # 重采样 44.1k -> 16k
    n_out = int(len(vocals) * 16000 / model.samplerate)
    idx = np.linspace(0, len(vocals) - 1, n_out).astype(int)
    vocals16 = vocals[idx].astype(np.float32)
    np.save(cache, vocals16)
    print("vocals separated & cached: %s (%.1fs)" % (tag, len(vocals16) / 16000.0))
    return vocals16

def chroma(y, hop=4096):
    import librosa
    return librosa.feature.chroma_cqt(y=y, sr=16000, hop_length=hop)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    args = ap.parse_args()
    sid = args.song

    songs = json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]
    smeta = next(s for s in songs if s["id"] == sid)
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    lyr = next(s for s in lyrics if s["id"] == sid)

    # 锚点对(块↔LRC)
    lrc_norm = {norm(txt): t for t, txt in fetch_lrc(lyr["netease_id"]) if norm(txt)}
    blocks = [b for b in load_blocks() if b["kind"] == "lyric" and b["song"] == sid]
    pairs = []
    for b in blocks:
        bn = norm(b["ja"])
        if bn and bn in lrc_norm:
            pairs.append((b["start"], lrc_norm[bn], len(bn)))
    if len(pairs) < 3:
        print("锚点不足")
        return
    pairs.sort(key=lambda p: p[0])
    span = pairs[-1][0] - pairs[0][0]
    k = max(3, min(10, int(span // 45)))
    anchors = [(pairs[0][0], pairs[0][1])]
    for i in range(1, k):
        lo = pairs[0][0] + span * i / k
        hi = pairs[0][0] + span * (i + 1) / k
        bucket = [p for p in pairs if lo <= p[0] < hi]
        if bucket:
            a = max(bucket, key=lambda p: p[2])
            if a[0] > anchors[-1][0]:
                anchors.append((a[0], a[1]))
    if anchors[-1][0] < pairs[-1][0]:
        anchors.append((pairs[-1][0], pairs[-1][1]))

    # live 段分离(整曲)
    live_audio = read_wav_seg(WAV, smeta["t0"], smeta["t1"])
    studio_audio = read_wav_seg(ROOT + r"\state\dtw\%s_studio.wav" % sid, 0, 10**9)
    live_voc = separate_vocals(live_audio, "%s_live" % sid)
    studio_voc = separate_vocals(studio_audio, "%s_studio" % sid)

    # 分段人声 DTW
    import librosa
    hop = 4096
    live_segs_t, studio_segs_t = [], []
    for i in range(len(anchors) - 1):
        la, sa = anchors[i]
        lb, sb = anchors[i + 1]
        if lb - la < 1 or sb - sa < 1:
            continue
        li0 = int((la - smeta["t0"]) * 16000)
        li1 = int((lb - smeta["t0"]) * 16000)
        si0 = int(sa * 16000)
        si1 = int(sb * 16000)
        if li1 > len(live_voc) or si1 > len(studio_voc):
            continue
        cl = chroma(live_voc[li0:li1], hop)
        cs = chroma(studio_voc[si0:si1], hop)
        if cl.shape[1] < 5 or cs.shape[1] < 5:
            continue
        D, wp = librosa.sequence.dtw(X=cl, Y=cs, metric="cosine",
                                     global_constraints=True, band_rad=0.25)
        live_segs_t.append(la + wp[:, 0] * (hop / 16000.0))
        studio_segs_t.append(sa + wp[:, 1] * (hop / 16000.0))
    if not live_segs_t:
        print("无有效段")
        return
    live_t = np.concatenate(live_segs_t)
    studio_t = np.concatenate(studio_segs_t)
    order = np.argsort(live_t)
    live_t, studio_t = live_t[order], studio_t[order]

    # 偏差
    devs = []
    for b in blocks:
        bn = norm(b["ja"])
        if bn and bn in lrc_norm:
            mapped = float(np.interp(b["start"], live_t, studio_t))
            devs.append(abs(mapped - lrc_norm[bn]))
    devs = np.array(devs)
    print("人声DTW: 匹配=%d 平均=%.2fs 中位=%.2fs 最大=%.2fs >3s=%d" % (
        len(devs), devs.mean(), np.median(devs), devs.max(), (devs > 3).sum()))

    # 保存
    step = max(1, len(live_t) // 240)
    idx = list(range(0, len(live_t), step)) + [len(live_t) - 1]
    out = {"song": sid, "live_t": [round(float(live_t[i]), 2) for i in idx],
           "studio_t": [round(float(studio_t[i]), 2) for i in idx],
           "median_dev": round(float(np.median(devs)), 2)}
    with open(ROOT + r"\state\dtw\%s.vocal.anchored.json" % sid, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("saved %s.vocal.anchored.json" % sid)

if __name__ == "__main__":
    main()
