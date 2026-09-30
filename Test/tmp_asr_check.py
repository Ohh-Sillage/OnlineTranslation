# -*- coding: utf-8 -*-
"""ASR 优化参数冒烟测试：8s 合成音频识别耗时（临时脚本，测试后可删除）
运行: python Test\tmp_asr_check.py
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

import config
from asr import ASR

print("beam_size:", config.BEAM_SIZE, "| threads:", config.ASR_CPU_THREADS,
      "| VAD_MAX_SEGMENT_S:", config.VAD_MAX_SEGMENT_S)

fs = 16000
t = np.arange(fs * 8) / fs
sig = (0.5 * np.sin(2 * np.pi * 220 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
pcm = sig * 0.2

t0 = time.time()
text = ASR.instance().transcribe(pcm, "ja")
print(f"识别结果: '{text}'  | 8s 音频识别耗时 {time.time() - t0:.1f}s（含模型加载则另计）")
