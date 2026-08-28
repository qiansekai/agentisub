# -*- coding: utf-8 -*-
"""relisten_probe.py — M1 验收: 对 Capullo 可疑块跑 faster-whisper 局部重听, 输出候选文本。

用法: python relisten_probe.py
"""
import wave
import numpy as np
import faster_whisper

WAV = r"D:\Kita-Tools\Media\Anima3\anima3_16k.wav"
MODEL = "large-v3-turbo"

# 目标块 (id, start, end, 原听写)
TARGETS = [
    ("15-014", 9251.3, 9257.9, "口すさめる時の赤い前の口色"),
    ("15-015", 9260.0, 9262.8, "もう泣かないでいるから"),
    ("15-017", 9268.7, 9271.0, "いつか明けるまで"),
    ("15-019", 9276.8, 9278.9, "敗退線、救済…"),
    ("15-020", 9280.7, 9283.1, "届くのは抜けない意味もない 心の媒体"),
    ("15-021", 9283.1, 9287.4, "そんなものに溺れる 息も抜けなくなったら"),
    ("15-022", 9287.4, 9289.0, "私は愛してることに変えたら"),
]

# 上下文提示（Capullo 前文，帮助解码）
CTX = "ヰ世界情緒 Capullo 歌詞。繰り返した景色 理解に背を向けて 自意識をした 嫌いになれたくて 繰り返した実像 理解しなくていいよ いつか忘れるでしょ 会わなくなったねと 震えも忘れたの わずかに熱を帯びてる 彗星だった 涙した指先がビジョンをかき分けていく せめて愛したのかも"

w = wave.open(WAV, "rb")
sr = w.getframerate()
assert sr == 16000, f"unexpected sample rate {sr}"

def read_seg(t0, t1):
    w.setpos(int(t0 * sr))
    n = int((t1 - t0) * sr)
    data = w.readframes(n)
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

print("loading model...")
model = faster_whisper.WhisperModel(MODEL, device="cpu", compute_type="int8")

for bid, t0, t1, orig in TARGETS:
    audio = read_seg(max(0, t0 - 1.0), t1 + 1.0)
    segs, info = model.transcribe(audio, language="ja", beam_size=5,
                                  initial_prompt=CTX, without_timestamps=True,
                                  condition_on_previous_text=False)
    texts = [s.text.strip() for s in segs]
    print("=" * 60)
    print("%s [%s-%s]" % (bid, t0, t1))
    print("  orig : %s" % orig)
    for i, t in enumerate(texts):
        print("  asr%d : %s" % (i + 1, t))
