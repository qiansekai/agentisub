# -*- coding: utf-8 -*-
"""fa_provider.py — Provider 实现: Qwen3-ForcedAligner 词级对齐(qwen-env 运行)。

stdin JSON: {"op":"align","t0":..,"t1":..,"lines":["歌词行1",...]}
stdout JSON: {"aligned":[{"line":..,"start":..,"end":..}]}
"""
import json
import sys
import wave

import numpy as np
import torch
from transformers import AutoProcessor, AutoModelForTokenClassification

WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
MODEL_ID = "Qwen/Qwen3-ForcedAligner-0.6B-hf"

def main():
    payload = json.loads(sys.stdin.read())
    t0, t1 = float(payload["t0"]), float(payload["t1"])
    lines = payload.get("lines", [])
    transcript = " ".join(lines)

    w = wave.open(WAV, "rb")
    sr = w.getframerate()
    w.setpos(int(t0 * sr))
    data = w.readframes(int((t1 - t0) * sr))
    w.close()
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    proc = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForTokenClassification.from_pretrained(
        MODEL_ID, device_map="cuda", dtype=torch.bfloat16).eval()
    inputs, word_lists = proc.prepare_forced_aligner_inputs(
        audio=audio, transcript=transcript, language="ja")
    inputs = inputs.to(model.device, model.dtype)
    with torch.inference_mode():
        logits = model(**inputs).logits
    ts = proc.decode_forced_alignment(logits, inputs["input_ids"], word_lists,
                                      timestamp_token_id=151705,
                                      timestamp_segment_time=proc.timestamp_segment_time or 0.03)
    out = []
    for row in ts:
        for w in row:
            s, e = float(w.get("start_time", 0)), float(w.get("end_time", 0))
            if e > s:
                out.append({"word": w.get("text", ""),
                            "start": round(t0 + s, 2), "end": round(t0 + e, 2)})
    print(json.dumps({"aligned": out}, ensure_ascii=False))

if __name__ == "__main__":
    main()
