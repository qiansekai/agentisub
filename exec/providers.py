# -*- coding: utf-8 -*-
"""providers.py — ASR/对齐 Provider 抽象层(调度器)。

统一 CLI 契约(JSON stdin -> stdout):
  {"op": "transcribe", "t0": 5264.0, "t1": 5296.0, "lang": "ja", "prompt": "..."}
    -> {"segments": [{"start":..., "end":..., "text":...}]}
  {"op": "align", "t0":..., "t1":..., "lines": ["行1", ...]}
    -> {"aligned": [{"line":..., "start":..., "end":...}]}

Provider 注册表(name -> venv python + 脚本)。未来新模型 = 新增 provider 脚本 + 注册一行。
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANIMA3 = r"D:\Kita-Tools\Media\Anima3"

PROVIDERS = {
    # 说话段 MC 转写: faster-whisper large-v3-turbo (GPU via ctranslate2)
    "whisper": {
        "python": ANIMA3 + r"\.venv\Scripts\python.exe",
        "script": os.path.join(ROOT, "exec", "providers", "whisper_provider.py"),
        "note": "MC 说话段最优(1错级别)",
    },
    # 唱歌段转写: Qwen3-ASR-1.7B (GPU fp16, qwen-env)
    "qwen": {
        "python": r"D:\Kita-Tools\Media\qwen-env\Scripts\python.exe",
        "script": os.path.join(ROOT, "exec", "providers", "qwen_provider.py"),
        "note": "唱歌段最优",
    },
    # 词级对齐: Qwen3-ForcedAligner (日语, qwen-env)
    "fa": {
        "python": r"D:\Kita-Tools\Media\qwen-env\Scripts\python.exe",
        "script": os.path.join(ROOT, "exec", "providers", "fa_provider.py"),
        "note": "词级时间戳(官方歌词文本 100% 正确)",
    },
}

def run(provider: str, payload: dict, timeout: int = 1800):
    """调用 provider, 返回 stdout JSON dict。"""
    if provider not in PROVIDERS:
        raise ValueError("unknown provider: %s (available: %s)" % (provider, ", ".join(PROVIDERS)))
    p = PROVIDERS[provider]
    proc = subprocess.run(
        [p["python"], p["script"]],
        input=json.dumps(payload, ensure_ascii=False).encode(),
        capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("provider %s failed: %s" % (provider, proc.stderr.decode("utf-8", "replace")[-500:]))
    return json.loads(proc.stdout.decode("utf-8", "replace"))

def transcribe(provider: str, t0: float, t1: float, lang: str = "ja", prompt: str = ""):
    return run(provider, {"op": "transcribe", "t0": t0, "t1": t1, "lang": lang, "prompt": prompt})

def align(provider: str, t0: float, t1: float, lines: list):
    return run(provider, {"op": "align", "t0": t0, "t1": t1, "lines": lines})

if __name__ == "__main__":
    print("providers:", json.dumps({k: v["note"] for k, v in PROVIDERS.items()}, ensure_ascii=False, indent=1))
