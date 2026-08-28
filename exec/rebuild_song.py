# -*- coding: utf-8 -*-
"""rebuild_song.py — 重建整曲块: piapro 歌词行 + align_song 直接对齐时间 + 未映射行插值。

07 曲专项: 迁移 bug 导致 56 块(重复+时间压缩在0.9s)。重建为 piapro 歌词行数块, 时间轴直接来自
live 音频的歌词对齐(aligned), 无映射行按相邻行插值。

用法: python rebuild_song.py --song 07 [--apply]
"""
import argparse
import json
import re
import sys
import unicodedata

ROOT = r"D:\Kita-Tools\Media\agentisub"
ANIMA3 = r"D:\Kita-Tools\Media\Anima3"

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return blocks

def read_piapro_lines(sid):
    """解析 Anima3/lyrics/NN.txt -> 歌词行列表(跳过元数据, '---' 后为正文)"""
    lines = []
    in_body = False
    with open(ANIMA3 + r"\lyrics\%s.txt" % sid, encoding="utf-8") as f:
        for raw in f:
            s = raw.rstrip("\n").rstrip("\r")
            if not in_body:
                if s.strip() == "---":
                    in_body = True
                continue
            s = s.strip()
            if s:
                lines.append(s)
    return lines

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    sid = args.song

    piapro = read_piapro_lines(sid)
    print("piapro 行数: %d" % len(piapro))

    aligned_path = ROOT + r"\state\retime_tmp\%s.aligned.json" % sid
    aligned = json.load(open(aligned_path, encoding="utf-8"))
    print("aligned 行数: %d" % len(aligned))
    aligned_by_norm = {norm(a["line"]): a for a in aligned}

    # 每行时间: aligned 精确 / 插值
    times = []
    for ln in piapro:
        a = aligned_by_norm.get(norm(ln))
        times.append((a["start"], a["end"]) if a else None)
    for i, t in enumerate(times):
        if t is not None:
            continue
        lo = hi = None
        for j in range(i - 1, -1, -1):
            if times[j] is not None:
                lo = j
                break
        for j in range(i + 1, len(times)):
            if times[j] is not None:
                hi = j
                break
        if lo is not None and hi is not None:
            s = times[lo][1] + (times[hi][0] - times[lo][1]) * (i - lo) / (hi - lo)
            times[i] = (round(s, 2), round(s + 1.5, 2))
        elif lo is not None:
            s = times[lo][1] + 2.0 * (i - lo)
            times[i] = (round(s, 2), round(s + 1.5, 2))
        elif hi is not None:
            s = times[hi][0] - 2.0 * (hi - i)
            times[i] = (round(s, 2), round(s + 1.5, 2))
    matched = sum(1 for t in times if t is not None)
    print("对齐 %d 行, 插值 %d 行" % (sum(1 for ln in piapro if norm(ln) in aligned_by_norm), len(piapro) - sum(1 for ln in piapro if norm(ln) in aligned_by_norm)))

    # zh 迁移: 旧块文本匹配
    old = load_blocks()
    old_by_norm = {}
    for b in old:
        if b["kind"] == "lyric" and b["song"] == sid:
            n = norm(b["ja"])
            if n and n not in old_by_norm:
                old_by_norm[n] = b

    new_blocks = []
    for i, ln in enumerate(piapro):
        st, en = times[i]
        ob = old_by_norm.get(norm(ln))
        zh = ob["zh"] if ob else ""
        new_blocks.append({
            "id": "%s-%03d" % (sid, i + 1),
            "start": st, "end": en,
            "kind": "lyric", "song": sid, "ja": ln, "zh": zh,
            "confidence": ob["confidence"] if ob else "green",
            "evidence": {"method": "rebuild_aligned", "detail": "live音频歌词对齐重建(迁移bug修复)"},
            "tags": ob["tags"] if ob else [],
            "history": [{"actor": "rebuild", "ts": "2026-08-29T00:00:00+08:00",
                         "note": "迁移bug重建: 旧块(重复+时间压缩) -> %d块" % len(piapro)}],
            "locked": False,
        })
    print("新块数: %d" % len(new_blocks))
    for nb in new_blocks[:8]:
        print("  %s [%s-%s] %s | %s" % (nb["id"], nb["start"], nb["end"], nb["ja"][:22], nb["zh"][:12]))

    if args.apply:
        other = [b for b in old if not (b["kind"] == "lyric" and b["song"] == sid)]
        merged = other + new_blocks
        merged.sort(key=lambda b: b["start"])
        with open(ROOT + r"\state\blocks.jsonl", "w", encoding="utf-8") as f:
            for b in merged:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
        print("已写 blocks.jsonl (%d 块, 需重启服务)" % len(merged))

if __name__ == "__main__":
    main()
