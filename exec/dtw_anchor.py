# -*- coding: utf-8 -*-
"""dtw_anchor.py — 锚点分段 DTW: 全局映射在 live 大改编(删前奏/改间奏)时漂移,
用"块文本↔LRC歌词行"匹配对做锚点, 分段独立对齐 + 锚点强制对齐, 拼接出精确映射。

用法:
  python dtw_anchor.py --song 08                 # 单曲锚点分段对齐
  python dtw_anchor.py --all                     # 对 8 首改编曲批量
  python dtw_anchor.py --song 07 --fix           # 用锚点映射修复 07 曲剩余块时间(patches)

输出: state/dtw/{song}.anchored.json (完整映射) + 偏差对比(全局 vs 锚点)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
import wave

import numpy as np

ROOT = r"D:\Kita-Tools\Media\agentisub"
WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://music.163.com/"}

# 改编大、需要锚点分段的曲(来自 verify 报告中位偏差 >3s 的)
ANCHOR_SONGS = ["08", "12", "13", "13b", "16", "18", "19", "20"]

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

def chroma(y, hop=4096):
    import librosa
    return librosa.feature.chroma_cqt(y=y, sr=16000, hop_length=hop)

def anchored_dtw(sid, n_anchors=None):
    """对 sid 做锚点分段 DTW, 返回 (live_t, studio_t) 完整映射数组。"""
    import librosa
    songs = json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]
    smeta = next(s for s in songs if s["id"] == sid)
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    lyr = next(s for s in lyrics if s["id"] == sid)
    blocks = [b for b in load_blocks() if b["kind"] == "lyric" and b["song"] == sid]
    lrc = fetch_lrc(lyr["netease_id"])
    lrc_norm = {norm(txt): t for t, txt in lrc if norm(txt)}

    # ---- 锚点: 块↔LRC 文本匹配对, 按 live 时间均匀选 ----
    pairs = []  # (live_t, studio_t, text_len)
    for b in blocks:
        bn = norm(b["ja"])
        if bn and bn in lrc_norm:
            pairs.append((b["start"], lrc_norm[bn], len(bn)))
    if len(pairs) < 3:
        return None
    pairs.sort(key=lambda p: p[0])
    span = pairs[-1][0] - pairs[0][0]
    k = n_anchors or max(3, min(10, int(span // 45)))
    # 分桶均匀选, 桶内取文本最长(最独特)的
    anchors = []
    for i in range(k):
        lo = pairs[0][0] + span * i / k
        hi = pairs[0][0] + span * (i + 1) / k
        bucket = [p for p in pairs if lo <= p[0] < hi]
        if bucket:
            anchors.append(max(bucket, key=lambda p: p[2]))
    anchors = [(pairs[0][0], pairs[0][1])] + [(a[0], a[1]) for a in anchors if a[0] > pairs[0][0]]
    if anchors[-1][0] < pairs[-1][0]:
        anchors.append((pairs[-1][0], pairs[-1][1]))
    # 锚点顺序一致性: live 和 studio 都递增
    anchors = [a for a in anchors if a[1] > 0]
    anchors.sort(key=lambda a: a[0])

    # ---- 分段 DTW ----
    hop = 4096
    live_segs = []
    studio_segs = []
    live_t_all = []
    studio_t_all = []
    for i in range(len(anchors) - 1):
        la, sa = anchors[i]
        lb, sb = anchors[i + 1]
        if lb - la < 1.0 or sb - sa < 1.0:
            continue
        ly = read_wav_seg(WAV, la, lb)
        sy = read_wav_seg(ROOT + r"\state\dtw\%s_studio.wav" % sid, sa, sb)
        cl = chroma(ly, hop)
        cs = chroma(sy, hop)
        if cl.shape[1] < 5 or cs.shape[1] < 5:
            continue
        D, wp = librosa.sequence.dtw(X=cl, Y=cs, metric="cosine",
                                     global_constraints=True, band_rad=0.25)
        lt = la + wp[:, 0] * (hop / 16000.0)
        st = sa + wp[:, 1] * (hop / 16000.0)
        live_t_all.append(lt)
        studio_t_all.append(st)
    if not live_t_all:
        return None
    live_t = np.concatenate(live_t_all)
    studio_t = np.concatenate(studio_t_all)
    # 去重排序
    order = np.argsort(live_t)
    return live_t[order], studio_t[order]

def verify_with_map(sid, live_t, studio_t, label):
    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    lyr = next(s for s in lyrics if s["id"] == sid)
    lrc = fetch_lrc(lyr["netease_id"])
    lrc_norm = {norm(txt): t for t, txt in lrc if norm(txt)}
    blocks = [b for b in load_blocks() if b["kind"] == "lyric" and b["song"] == sid]
    devs = []
    for b in blocks:
        bn = norm(b["ja"])
        if bn and bn in lrc_norm:
            mapped = float(np.interp(b["start"], live_t, studio_t))
            devs.append(abs(mapped - lrc_norm[bn]))
    if not devs:
        return None
    devs = np.array(devs)
    print("  [%s] 匹配=%d 平均=%.2fs 中位=%.2fs 最大=%.2fs >3s=%d" % (
        label, len(devs), devs.mean(), np.median(devs), devs.max(), (devs > 3).sum()))
    return {"label": label, "mean": round(float(devs.mean()), 2),
            "median": round(float(np.median(devs)), 2), "n": int(len(devs))}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    targets = ANCHOR_SONGS if args.all else [args.song] if args.song else ANCHOR_SONGS
    summary = []
    for sid in targets:
        print("=" * 56)
        print("SONG %s" % sid)
        # 全局映射基线
        gmap = None
        try:
            g = json.load(open(ROOT + r"\state\dtw\%s.map.json" % sid, encoding="utf-8"))
            gmap = (np.array(g["live_t"]), np.array(g["studio_t"]))
        except Exception:
            pass
        r = anchored_dtw(sid)
        if r is None:
            print("  锚点不足, 跳过")
            continue
        live_t, studio_t = r
        row = {"song": sid}
        if gmap is not None:
            b = verify_with_map(sid, gmap[0], gmap[1], "全局")
            if b:
                row["global"] = b
        a = verify_with_map(sid, live_t, studio_t, "锚点")
        if a:
            row["anchored"] = a
        # 保存 anchored 映射(采样 240 点)
        step = max(1, len(live_t) // 240)
        idx = list(range(0, len(live_t), step)) + [len(live_t) - 1]
        out = {"song": sid, "live_t": [round(float(live_t[i]), 2) for i in idx],
               "studio_t": [round(float(studio_t[i]), 2) for i in idx]}
        with open(ROOT + r"\state\dtw\%s.anchored.json" % sid, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("  saved %s.anchored.json" % sid)
        summary.append(row)

    with open(ROOT + r"\state\dtw\anchor_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("\n锚点分段完成, 汇总存 state/dtw/anchor_summary.json")

if __name__ == "__main__":
    main()
