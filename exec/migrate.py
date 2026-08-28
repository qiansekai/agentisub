# -*- coding: utf-8 -*-
"""migrate.py — 把 Anima3 成品字幕迁移为 agentisub 状态文件 blocks.jsonl + meta.json。

置信度规则（规划 v1.0 决策 6）：
- MC（两遍转写交叉）→ green
- 歌词：ASR 锚点行（词级时间戳证据支持）→ green；插值行 → yellow
- 15 Capullo（听写稿）→ red
块 id：歌词 = 曲目-歌词行号（稳定）；MC = M-序号
"""
import difflib
import json
import os
import re
import sys

ANIMA = r"D:\Kita-Tools\Media\Anima3"
SUBQC = r"D:\Kita-Tools\Media\agentisub"
sys.path.insert(0, ANIMA)

from align_song import read_lyrics, norm_text, align_lines  # noqa: E402

def parse_srt(path):
    out = []
    with open(path, encoding="utf-8") as f:
        content = f.read()
    for b in re.split(r"\n\s*\n", content.strip()):
        lines = [l for l in b.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
        if not m:
            continue
        s = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000.0
        e = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000.0
        out.append((s, e, "\n".join(lines[2:])))
    return out

def main():
    bounds = {b["id"]: b for b in json.load(open(os.path.join(ANIMA, "boundaries.json"), encoding="utf-8"))}

    # 译文表（按日文原文）
    zh_by_ja = {}
    tdir = os.path.join(ANIMA, "translated")
    for fn in os.listdir(tdir):
        if not fn.startswith("out_") or not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(tdir, fn), encoding="utf-8"))
        except Exception:
            continue
        for b in d.get("blocks", []):
            if b.get("zh"):
                zh_by_ja.setdefault(b["ja"].strip(), b["zh"])

    # 词级时间戳（全片，用于锚点证据）
    words = []
    with open(os.path.join(ANIMA, "anima3.words.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    w = json.loads(line)
                    words.append((float(w["start"]), float(w["end"]), w["word"]))
                except Exception:
                    pass

    def words_in(a, b):
        return [{"start": s, "end": e, "word": w} for s, e, w in words if s < b and e > a]

    def song_of(t):
        for sid, b in bounds.items():
            if b.get("t0") is not None and b["t0"] - 4 <= t <= b["t1"] + 4:
                return sid
        return None

    # 每首歌：词级对齐结果（判断锚点行）
    anchor_map = {}  # sid -> set(line_index)
    for sid, b in bounds.items():
        if sid == "15":
            continue
        lp = os.path.join(ANIMA, "lyrics", sid + ".txt")
        if not os.path.exists(lp):
            continue
        lines = read_lyrics(lp)
        ws = words_in(float(b["t0"]), float(b["t1"]))
        aligned = align_lines(lines, ws, t0=float(b["t0"]))
        for a in aligned:
            try:
                idx = lines.index(a["line"])
                anchor_map.setdefault(sid, set()).add(idx)
            except ValueError:
                pass

    blocks = parse_srt(os.path.join(ANIMA, "anima3_full.srt"))
    out = []
    song_counters = {}
    mc_seq = 0
    for s, e, ja in blocks:
        sid = song_of((s + e) / 2)
        if sid:
            counters_key = sid
            idx = song_counters.get(counters_key, 0)
            song_counters[counters_key] = idx + 1
            bid = "%s-%03d" % (sid, idx + 1)
            kind = "lyric"
            if sid == "15":
                conf, method, detail = "red", "asr_transcribe", "Capullo 听写稿（无官方歌词，三次ASR交叉）"
            elif idx in anchor_map.get(sid, set()):
                conf, method, detail = "green", "asr_anchor", "提示词ASR对齐 + 词级时间戳证据"
            else:
                conf, method, detail = "yellow", "interp", "相邻锚点插值估算"
        else:
            mc_seq += 1
            bid = "M-%04d" % mc_seq
            kind = "talk"
            conf, method, detail = "green", "asr_2pass_cross", "两遍转写（无提示+专名提示）交叉确认"
        out.append({
            "id": bid, "start": round(s, 3), "end": round(e, 3),
            "kind": kind, "song": sid, "ja": ja, "zh": zh_by_ja.get(ja.strip(), ""),
            "confidence": conf,
            "evidence": {"method": method, "detail": detail},
            "tags": [], "history": [], "locked": False,
        })

    os.makedirs(os.path.join(SUBQC, "state"), exist_ok=True)
    with open(os.path.join(SUBQC, "state", "blocks.jsonl"), "w", encoding="utf-8") as f:
        for b in out:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    meta = {
        "schema_version": 1,
        "project": "anima3",
        "media": {
            "video": os.path.join(SUBQC, "media", "proxy.mp4"),
            "audio_16k": os.path.join(ANIMA, "anima3_16k.wav"),
            "duration": 14571.3,
        },
        "counts": {"total": len(out),
                   "green": sum(1 for b in out if b["confidence"] == "green"),
                   "yellow": sum(1 for b in out if b["confidence"] == "yellow"),
                   "red": sum(1 for b in out if b["confidence"] == "red")},
    }
    with open(os.path.join(SUBQC, "state", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("[done] %d 块: %s" % (len(out), meta["counts"]), flush=True)

if __name__ == "__main__":
    main()
