# -*- coding: utf-8 -*-
"""precompute.py — 波形 peaks 与频谱数据预计算（M1）。
输入：Anima3 16k 单声道 WAV（233M 样本，约 4h）
输出：
  state/peaks.json   时间轴波形 min/max（20px/s 桶）
  state/spectrum.bin 频谱 log 幅度（5fps × 96 频带，uint8）
  state/spectrum.meta.json
"""
import json
import math
import os
import struct
import wave

import numpy as np

ANIMA = r"D:\Kita-Tools\Media\Anima3"
SUBQC = r"D:\Kita-Tools\Media\agentisub"

PIX_PER_SEC = 20.0          # 波形时间分辨率
SPEC_FPS = 5.0              # 频谱帧率
SPEC_BANDS = 96             # 频谱频带数
FFT_FRAME = 4096

def main():
    wav_path = os.path.join(ANIMA, "anima3_16k.wav")
    with wave.open(wav_path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        sr = w.getframerate()
        n_frames = w.getnframes()
        print("[wav] %d samples, %.1fs" % (n_frames, n_frames / sr), flush=True)
        # 全量读入（233M samples × 2B = 466MB，内存可行）
        raw = np.frombuffer(w.readframes(n_frames), dtype=np.int16)

    # ---- 波形 peaks ----
    bucket = int(sr / PIX_PER_SEC)  # 800 samples/pixel
    n_buckets = (len(raw) + bucket - 1) // bucket
    padded = np.zeros(n_buckets * bucket, dtype=np.int16)
    padded[:len(raw)] = raw
    arr = padded.reshape(n_buckets, bucket)
    peaks = np.stack([arr.min(axis=1), arr.max(axis=1)], axis=1)  # n×2 int16
    with open(os.path.join(SUBQC, "state", "peaks.bin"), "wb") as f:
        f.write(peaks.astype(np.int16).tobytes())
    print("[peaks] %d buckets -> state/peaks.bin (%.1f MB)" % (n_buckets, peaks.nbytes / 1e6), flush=True)

    # ---- 频谱（5fps × 96 频带，uint8 log 幅度）----
    hop = int(sr / SPEC_FPS)  # 3200
    n_frames_spec = 1 + max(0, (len(raw) - FFT_FRAME) // hop)
    win = np.hanning(FFT_FRAME).astype(np.float32)
    spec = np.zeros((n_frames_spec, SPEC_BANDS), dtype=np.uint8)
    chunk = 4096  # 每次算 4096 帧
    for start in range(0, n_frames_spec, chunk):
        end = min(start + chunk, n_frames_spec)
        idx0 = start * hop
        # 取帧块：end 帧
        buf = np.zeros((end - start, FFT_FRAME), dtype=np.float32)
        for i in range(start, end):
            s = i * hop
            seg = raw[s:s + FFT_FRAME].astype(np.float32) / 32768.0
            buf[i - start, :len(seg)] = seg * win[:len(seg)]
        mag = np.abs(np.fft.rfft(buf, axis=1))[:, :FFT_FRAME // 2]  # (n, 2048)
        # 线性频带压缩到 96 带（每带平均）
        nbins = mag.shape[1]
        per = nbins // SPEC_BANDS
        m2 = mag[:, :per * SPEC_BANDS].reshape(end - start, SPEC_BANDS, per).mean(axis=2)
        logm = np.log1p(m2 * 8.0)  # 压缩动态范围
        lo, hi = logm.min(), logm.max()
        scale = 255.0 / max(hi - lo, 1e-6)
        spec[start:end] = np.clip((logm - lo) * scale, 0, 255).astype(np.uint8)
        if start % (chunk * 8) == 0:
            print("[spec] %d/%d frames" % (end, n_frames_spec), flush=True)
    with open(os.path.join(SUBQC, "state", "spectrum.bin"), "wb") as f:
        f.write(spec.tobytes())
    with open(os.path.join(SUBQC, "state", "spectrum.meta.json"), "w", encoding="utf-8") as f:
        json.dump({"fps": SPEC_FPS, "bands": SPEC_BANDS, "frames": n_frames_spec,
                   "duration": n_frames / sr}, f)
    print("[spec] %d×%d -> state/spectrum.bin (%.1f MB)" % (n_frames_spec, SPEC_BANDS, spec.nbytes / 1e6), flush=True)
    print("[done]", flush=True)

if __name__ == "__main__":
    main()
