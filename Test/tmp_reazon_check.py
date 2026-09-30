# -*- coding: utf-8 -*-
"""ReazonSpeech 日语引擎冒烟测试（临时脚本，测试后可删除）
运行: python Test\tmp_reazon_check.py
"""
import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

import config
from asr import ASR

wav_dir = os.path.join(config.REAZON_MODEL_DIR, "test_wavs")
wavs = sorted(f for f in os.listdir(wav_dir) if f.endswith(".wav"))
print("样例音频:", wavs)

for fn in wavs[:3]:
    with wave.open(os.path.join(wav_dir, fn), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:  # 简单线性重采样到 16k
        x = np.arange(round(len(samples) * 16000 / sr)) * sr / 16000
        samples = np.interp(x, np.arange(len(samples)), samples).astype(np.float32)
    print(f"{fn}: {len(samples) / 16000:.1f}s")
    t0 = time.time()
    text = ASR.instance().transcribe(samples, "ja")
    print(f"  识别耗时 {time.time() - t0:.2f}s: {text[:80]}")
