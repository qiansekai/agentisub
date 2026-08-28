# -*- coding: utf-8 -*-
"""probe_intro.py — 识别用户标记的开场介绍段(4987-5004s): 提取音频 + whisper 转写。"""
import wave
import numpy as np
import faster_whisper

WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
t0, t1 = 5560.0, 5935.0

w = wave.open(WAV, "rb")
sr = w.getframerate()
w.setpos(int(t0 * sr))
data = w.readframes(int((t1 - t0) * sr))
w.close()
audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

model = faster_whisper.WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
segs, info = model.transcribe(audio, language="ja", beam_size=5, word_timestamps=True)
for s in segs:
    print("[%.1f-%.1f] %s" % (t0 + s.start, t0 + s.end, s.text))
    for wd in (s.words or []):
        print("   %.1f %s" % (t0 + wd.start, wd.word))
