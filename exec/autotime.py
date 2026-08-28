# -*- coding: utf-8 -*-
"""autotime.py — 自主打轴: 用网易云 LRC 时间戳 + DTW 映射 自动生成/修正整曲 live 时间轴。

输入: --song 05
流程:
  1. 读该曲歌词行(state/lyrics.json) + 网易云 LRC 时间戳(缓存 state/lrc/{song}.json)
  2. 读 DTW 映射(state/dtw/{song}.anchored.json 优先, 否则 .map.json)
  3. LRC studio 时间 -> 映射 -> live 时间(每歌词行)
  4. 按文本匹配现有块, 生成 patches(块 -> 新 start/end)
输出: patches JSON(可直接 POST /api/patches); --apply 直接回写
"""
import argparse
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
    """抓 LRC 时间戳, 缓存到 state/lrc/{sid}.json"""
    cache_dir = ROOT + r"\state\lrc"
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, "%s.json" % sid)
    if os.path.exists(cache):
        data = json.load(open(cache, encoding="utf-8"))
        # 兼容两种缓存: 新格式 dict{lrc:[..]} / 旧格式 list[[t,txt]..]
        if isinstance(data, dict):
            return data.get("lrc", [])
        return data
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
            out.append([t, txt])
    json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return out

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return blocks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--create", action="store_true", help="无匹配块的歌词行创建新块(开场曲01-04)")
    ap.add_argument("--threshold", type=float, default=0.3, help="偏差超过该秒数才生成 patch")
    args = ap.parse_args()
    sid = args.song

    lyrics = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))["songs"]
    lyr = next((s for s in lyrics if s["id"] == sid), None)
    if not lyr:
        print("无网易云歌词(Capullo), 无法自动打轴")
        sys.exit(2)

    # DTW 映射
    amap = None
    for fname in ("%s.anchored.json", "%s.map.json"):
        p = os.path.join(ROOT, "state", "dtw", fname % sid)
        try:
            m = json.load(open(p, encoding="utf-8"))
            amap = (np.array(m["studio_t"]), np.array(m["live_t"]))
            print("映射: %s" % fname)
            break
        except Exception:
            continue
    if amap is None:
        print("无 DTW 映射, 请先跑 dtw_align/dtw_anchor")
        sys.exit(1)
    studio_arr, live_arr = amap

    # LRC 时间戳 -> 每歌词行 studio 时间(保留重复行: 副歌写多遍)
    lrc = fetch_lrc_cached(lyr["netease_id"], sid)
    lrc_all = {}  # norm -> [t1, t2, ...] (重复副歌的多次出现)
    for t, txt in lrc:
        n = norm(txt)
        if n:
            lrc_all.setdefault(n, []).append(t)

    # 块按 live 时间排序, 同一 norm 的块按出现次序依次分配 LRC 时间戳
    blocks = sorted([b for b in load_blocks() if b["kind"] == "lyric" and b["song"] == sid],
                    key=lambda b: b["start"])
    used = {}
    patches = []
    matched = 0
    for b in blocks:
        bn = norm(b["ja"])
        ts_list = lrc_all.get(bn)
        if not ts_list:
            continue
        k = used.get(bn, 0)
        st_t = ts_list[k] if k < len(ts_list) else ts_list[-1]
        used[bn] = k + 1
        new_start = float(np.interp(st_t, studio_arr, live_arr))
        # 块时长: 用下一歌词行时间差(studio)换算
        # 找该歌词行在 lyr.lines 的位置
        li = next((i for i, ln in enumerate(lyr["lines"]) if norm(ln) == bn), None)
        if li is not None and li + 1 < len(lyr["lines"]):
            n2 = norm(lyr["lines"][li + 1])
            st2 = lrc_all.get(n2, [None])[0]
            if st2 is not None:
                new_end = float(np.interp(st2, studio_arr, live_arr))
            else:
                new_end = new_start + max(1.0, b["end"] - b["start"])
        else:
            new_end = new_start + max(1.0, b["end"] - b["start"])
        matched += 1
        if abs(new_start - b["start"]) > args.threshold or abs(new_end - b["end"]) > args.threshold:
            patches.append({
                "id": "P-AUTOTIME-%s" % b["id"],
                "block_id": b["id"],
                "tag_id": "",
                "reply": "自主打轴(LRC+DTW): 原 [%.2f-%.2f] -> 新 [%.2f-%.2f]" % (
                    b["start"], b["end"], new_start, new_end),
                "changes": {"start": round(new_start, 2), "end": round(new_end, 2)},
            })
    print("块 %d, LRC匹配 %d, 需修正 %d" % (len(blocks), matched, len(patches)))
    for p in patches[:8]:
        print("  %s" % p["block_id"])

    # ---- create 模式: 无匹配块的歌词行 -> 创建新块 ----
    creates = []
    if args.create:
        existing_norms = {norm(b["ja"]) for b in blocks}
        for i, ln in enumerate(lyr["lines"]):
            n = norm(ln)
            if n in existing_norms or not n:
                continue
            ts_list = lrc_all.get(n)
            if not ts_list:
                continue
            new_start = float(np.interp(ts_list[0], studio_arr, live_arr))
            new_end = None
            for j in range(i + 1, len(lyr["lines"])):
                n2 = norm(lyr["lines"][j])
                ts2 = lrc_all.get(n2, [None])[0]
                if ts2 is not None:
                    new_end = float(np.interp(ts2, studio_arr, live_arr))
                    break
            if new_end is None or new_end <= new_start:
                new_end = new_start + 2.0
            creates.append({
                "id": "%s-%03d" % (sid, 900 + len(creates)),  # 占位, 服务端重分配
                "start": round(new_start, 2),
                "end": round(new_end, 2),
                "kind": "lyric",
                "song": sid,
                "ja": ln,
                "zh": lyr.get("lines_zh", [""] * len(lyr["lines"]))[i] if i < len(lyr.get("lines_zh", [])) else "",
                "confidence": "yellow",  # 官方歌词补块: 待校对(live 可能删段/改词)
            })
        print("create 模式: 新建 %d 块" % len(creates))
        for c in creates[:8]:
            print("  %s [%s-%s] %s" % (c["id"], c["start"], c["end"], c["ja"][:20]))

    if creates:
        if args.apply:
            import urllib.request as ur
            ok = 0
            for c in creates:
                body = json.dumps({k: c[k] for k in ("start", "end", "kind", "song", "ja", "zh", "confidence")}).encode()
                req = ur.Request("http://127.0.0.1:8720/api/blocks",
                                 data=body, headers={"Content-Type": "application/json"})
                with ur.urlopen(req, timeout=30) as r:
                    r.read()
                    ok += 1
            print("created via API: %d" % ok)
        else:
            with open(ROOT + r"\state\autotime_create_%s.json" % sid, "w", encoding="utf-8") as f:
                json.dump(creates, f, ensure_ascii=False, indent=1)
            print("creates -> state/autotime_create_%s.json (加 --apply 写入)" % sid)

    if patches:
        if args.apply:
            import urllib.request as ur
            req = ur.Request("http://127.0.0.1:8720/api/patches",
                             data=json.dumps(patches).encode(),
                             headers={"Content-Type": "application/json"})
            with ur.urlopen(req, timeout=30) as r:
                print("applied: %s" % r.read().decode())
        else:
            with open(ROOT + r"\state\autotime_%s.json" % sid, "w", encoding="utf-8") as f:
                json.dump(patches, f, ensure_ascii=False, indent=1)
            print("patches -> state/autotime_%s.json (加 --apply 回写)" % sid)

if __name__ == "__main__":
    main()
