# -*- coding: utf-8 -*-
"""relisten.py — M2 需重听标记修复: 多 pass ASR 交叉, 输出候选文本供 agent 判定。

用法:
  python relisten.py --block 15-014                 # 打印多 pass 候选
  python relisten.py --block 15-014 --out c.json    # 候选存 JSON

多 pass 组合:
  1. beam=5, 无提示
  2. beam=5, 歌词上下文提示(该曲网易云歌词, Capullo 无则跳过)
  3. beam=10, 歌词上下文提示
输出: {"block_id":..., "original":..., "candidates":[{"pass":n,"text":...}]}
"""
import argparse
import json
import sys
import wave

import numpy as np
import faster_whisper

ROOT = r"D:\Kita-Tools\Media\agentisub"
WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"

def load_blocks():
    blocks = []
    for ln in open(ROOT + r"\state\blocks.jsonl", encoding="utf-8"):
        ln = ln.strip()
        if ln:
            blocks.append(json.loads(ln))
    return {b["id"]: b for b in blocks}

def load_lyrics():
    try:
        d = json.load(open(ROOT + r"\state\lyrics.json", encoding="utf-8"))
        return {s["id"]: " ".join(s["lines"][:60]) for s in d["songs"]}
    except Exception:
        return {}

def read_seg(t0, t1, w):
    w.setpos(int(t0 * 16000))
    n = int((t1 - t0) * 16000)
    return np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    by_id = load_blocks()
    b = by_id.get(args.block)
    if not b:
        print("block not found: %s" % args.block)
        sys.exit(1)
    ctx = load_lyrics().get(b["song"], "")

    pad = 1.5
    t0, t1 = max(0, b["start"] - pad), b["end"] + pad
    w = wave.open(WAV, "rb")
    audio = read_seg(t0, t1, w)
    w.close()

    model = faster_whisper.WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    passes = [
        (5, ""),
        (5, ctx[:2000]),
        (10, ctx[:2000]),
    ]
    cands = []
    print("relisten %s [%s-%s] orig: %s" % (b["id"], b["start"], b["end"], b["ja"]))
    for i, (beam, prompt) in enumerate(passes):
        segs, _ = model.transcribe(audio, language="ja", beam_size=beam,
                                   initial_prompt=prompt, without_timestamps=True,
                                   condition_on_previous_text=False)
        text = "".join(s.text.strip() for s in segs)
        cands.append({"pass": i + 1, "beam": beam, "prompt": "ctx" if prompt else "none", "text": text})
        print("  pass%d (beam=%d, %s): %s" % (i + 1, beam, "ctx" if prompt else "none", text))

    out = {"block_id": b["id"], "song": b["song"], "original": b["ja"], "candidates": cands}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("wrote %s" % args.out)

if __name__ == "__main__":
    main()
