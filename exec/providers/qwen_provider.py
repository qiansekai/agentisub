# -*- coding: utf-8 -*-
"""qwen_provider.py — Provider 实现: Qwen3-ASR-1.7B 转写(qwen-env 运行)。

stdin JSON: {"op":"transcribe","t0":..,"t1":..,"lang":"ja"}
stdout JSON: {"segments":[...]}
"""
import json
import sys
import wave

import numpy as np
import torch
from transformers import AutoProcessor, AutoModelForMultimodalLM

WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
MODEL_ID = "Qwen/Qwen3-ASR-1.7B-hf"

def main():
    payload = json.loads(sys.stdin.read())
    t0, t1 = float(payload["t0"]), float(payload["t1"])
    lang = payload.get("lang", "ja")

    w = wave.open(WAV, "rb")
    sr = w.getframerate()
    w.setpos(int(t0 * sr))
    data = w.readframes(int((t1 - t0) * sr))
    w.close()
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    qproc = AutoProcessor.from_pretrained(MODEL_ID)
    qmodel = AutoModelForMultimodalLM.from_pretrained(MODEL_ID, device_map="cuda",
                                                      dtype=torch.float16).eval()
    inputs = qproc.apply_transcription_request(audio=audio, language=lang)
    inputs = inputs.to(qmodel.device, qmodel.dtype)
    with torch.inference_mode():
        out_ids = qmodel.generate(**inputs, max_new_tokens=1024, do_sample=False)
    gen = out_ids[:, inputs["input_ids"].shape[1]:]
    out = qproc.decode(gen, return_format="transcription_only")
    if isinstance(out, list):
        out = " ".join(out)
    # Qwen 输出无时间戳: 单段返回(时间=输入区间)
    print(json.dumps({"segments": [{"start": round(t0, 2), "end": round(t1, 2), "text": out}]},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()
