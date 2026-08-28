# -*- coding: utf-8 -*-
"""rebuild_live.py — 损坏曲重建 v2: whisper 整曲转录 segment 驱动, 保留 live 重复副歌。

方案: whisper(prompt=歌词) 转录整曲 -> segments 是 live 实际演唱序列(含重复副歌)
      -> 每 segment 文本匹配回 piapro 规范歌词行 -> 块 ja=规范行, 时间=segment词时间戳
      -> 未匹配 segment(live即兴) 保留 ASR 原文, confidence=yellow
用法: python rebuild_live.py --song 13 [--apply]
"""
import argparse
import json
import re
import sys
import unicodedata
import wave

import numpy as np

ROOT = r"D:\Kita-Tools\Media\agentisub"
ANIMA3 = r"D:\Kita-Tools\Media\Anima3"
WAV = ANIMA3 + r"\anima3_16k.wav"

def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[\s\u3000・、。，．！？!?「」『』（）()\[\]【】…—\-―〜~♪～\"'‘’“”,.:;/｜丨※×]", "", s)
    return s

def read_piapro(sid):
    lines, in_body = [], False
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

def read_wav_seg(t0, t1):
    w = wave.open(WAV, "rb")
    sr = w.getframerate()
    w.setpos(int(t0 * sr))
    n = int((t1 - t0) * sr)
    data = w.readframes(n)
    w.close()
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

def match_line(seg_text, lines):
    """segment 文本 -> 最佳匹配歌词行索引(包含关系评分), 无匹配 -1"""
    sn = norm(seg_text)
    if not sn:
        return -1
    best_i, best_r = -1, 0.0
    for i, ln in enumerate(lines):
        ln_n = norm(ln)
        if not ln_n:
            continue
        if sn == ln_n:
            return i
        if len(ln_n) >= 4 and (ln_n in sn or sn in ln_n):
            r = min(len(ln_n), len(sn)) / max(len(ln_n), len(sn))
            if r > best_r:
                best_i, best_r = i, r
    return best_i if best_r >= 0.55 else -1

def split_segment(seg, lines):
    """词级累积匹配: 把 segment 拆成多个 (line_idx, t0, t1) 块。
    逐词累加 norm 文本, 当累加包含 lines[li] 时记一块并推进 li。
    返回 [(line_idx, t0, t1)] (li 为 piapro 行索引)。"""
    out = []
    if not seg.words:
        return out
    acc = ""
    acc_start = None
    li = 0
    last_line_hit = None
    for w in seg.words:
        if acc_start is None:
            acc_start = w.start
        acc += w.word
        acc_n = norm(acc)
        hit = -1
        # 从 li 起找能匹配的行
        for j in range(li, len(lines)):
            ln_n = norm(lines[j])
            if ln_n and len(ln_n) >= 3 and ln_n in acc_n:
                hit = j
                break
        if hit >= 0:
            out.append((hit, acc_start, w.end))
            last_line_hit = hit
            acc = ""
            acc_start = None
            li = hit + 1
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    sid = args.song

    songs = json.load(open(ROOT + r"\state\songs.json", encoding="utf-8"))["songs"]
    sm = next(s for s in songs if s["id"] == sid)
    lines = read_piapro(sid)
    print("piapro 行数: %d" % len(lines))

    # 旧块(zh/tags 迁移)
    old = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            old.append(json.loads(ln))
    old_by_norm = {}
    for b in old:
        if b["kind"] == "lyric" and b["song"] == sid:
            n = norm(b["ja"])
            if n and n not in old_by_norm:
                old_by_norm[n] = b

    # whisper 整曲转录
    import faster_whisper
    audio = read_wav_seg(sm["t0"], sm["t1"])
    prompt = "".join(lines)[:2000]
    model = faster_whisper.WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language="ja", beam_size=5, initial_prompt=prompt,
                               word_timestamps=True, condition_on_previous_text=False)

    new_blocks = []
    idx = 1
    matched = unmatched = 0
    for s in segs:
        txt = s.text.strip()
        if not txt:
            continue
        # 词级拆分: segment 可能含多行歌词
        parts = split_segment(s, lines)
        if parts:
            for li, w0, w1 in parts:
                w0 = sm["t0"] + w0
                w1 = sm["t0"] + w1
                if w1 - w0 < 0.4:
                    continue
                ja = lines[li]
                conf = "green"
                matched += 1
                ob = old_by_norm.get(norm(ja))
                new_blocks.append({
                    "id": "%s-%03d" % (sid, idx), "start": round(w0, 2), "end": round(w1, 2),
                    "kind": "lyric", "song": sid, "ja": ja, "zh": ob["zh"] if ob else "",
                    "confidence": conf,
                    "evidence": {"method": "rebuild_live", "detail": "segment驱动重建(保留live重复)"},
                    "tags": ob["tags"] if ob else [],
                    "history": [{"actor": "rebuild", "ts": "2026-08-29T00:00:00+08:00",
                                 "note": "时间压缩损坏重建v2"}],
                    "locked": False,
                })
                idx += 1
            continue
        # 无词级匹配: 整段作为 live 即兴/改词块
        li = match_line(txt, lines)
        w0 = sm["t0"] + (s.words[0].start if s.words else s.start)
        w1 = sm["t0"] + (s.words[-1].end if s.words else s.end)
        if w1 - w0 < 0.4:
            continue
        if li >= 0:
            ja = lines[li]
            conf = "green"
            matched += 1
        else:
            ja = txt
            conf = "yellow"
            unmatched += 1
        ob = old_by_norm.get(norm(ja))
        new_blocks.append({
            "id": "%s-%03d" % (sid, idx), "start": round(w0, 2), "end": round(w1, 2),
            "kind": "lyric", "song": sid, "ja": ja, "zh": ob["zh"] if ob else "",
            "confidence": conf,
            "evidence": {"method": "rebuild_live", "detail": "segment驱动重建(保留live重复)"},
            "tags": ob["tags"] if ob else [],
            "history": [{"actor": "rebuild", "ts": "2026-08-29T00:00:00+08:00",
                         "note": "时间压缩损坏重建v2"}],
            "locked": False,
        })
        idx += 1

    print("segments -> 块 %d (匹配规范行 %d, live即兴 %d)" % (len(new_blocks), matched, unmatched))
    for nb in new_blocks[:12]:
        print("  %s [%s-%s] %s | %s" % (nb["id"], nb["start"], nb["end"], nb["ja"][:24], nb["zh"][:10]))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(new_blocks, f, ensure_ascii=False, indent=1)
        print("预览存至 %s" % args.out)
    elif args.apply:
        other = [b for b in old if not (b["kind"] == "lyric" and b["song"] == sid)]
        merged = other + new_blocks
        merged.sort(key=lambda b: b["start"])
        with open(ROOT + r"\state\blocks.jsonl", "w", encoding="utf-8") as f:
            for b in merged:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
        print("WRITTEN (%d 块, 需重启服务)" % len(merged))
    else:
        print("预览: 加 --out 存JSON 或 --apply 写入")

if __name__ == "__main__":
    main()
