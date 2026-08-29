# -*- coding: utf-8 -*-
"""whisper_provider.py — Provider 实现: faster-whisper 转写(Anima3 venv 运行)。

stdin JSON: {"op":"transcribe","t0":..,"t1":..,"lang":"ja","prompt":".."}
stdout JSON: {"segments":[...]}
"""
import json
import sys
import wave

import numpy as np

WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"

def main():
    payload = json.loads(sys.stdin.read())
    t0, t1 = float(payload["t0"]), float(payload["t1"])
    lang = payload.get("lang", "ja")
    prompt = payload.get("prompt", "")

    w = wave.open(WAV, "rb")
    sr = w.getframerate()
    w.setpos(int(t0 * sr))
    data = w.readframes(int((t1 - t0) * sr))
    w.close()
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    import faster_whisper
    model = faster_whisper.WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
    kwargs = {"language": lang, "beam_size": 5}
    if prompt:
        kwargs["initial_prompt"] = prompt[:1800]
        kwargs["condition_on_previous_text"] = False
    segs, _ = model.transcribe(audio, **kwargs)
    out = []
    for s in segs:
        txt = s.text.strip()
        if txt:
            out.append({"start": round(t0 + s.start, 2), "end": round(t0 + s.end, 2), "text": txt})
    print(json.dumps({"segments": out}, ensure_ascii=False))

if __name__ == "__main__":
    main()
