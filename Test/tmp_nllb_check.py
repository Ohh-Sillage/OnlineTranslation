# -*- coding: utf-8 -*-
"""NLLB 本地模型加载与翻译冒烟测试（临时脚本，测试后可删除）
运行: python Test\tmp_nllb_check.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

import config
from translator import Translator

print("翻译策略:", config.TRANSLATOR)
print("NLLB 路径:", config.NLLB_MODEL_PATH)

tr = Translator.instance()
print("instance 创建 OK（懒加载，未阻塞事件循环）")

t0 = time.time()
out = tr.translate("こんにちは。これはリアルタイム字幕翻訳のテストです。", "ja")
print(f"[ja->zh] {out}  （含模型首次加载 {time.time() - t0:.1f}s）")

t0 = time.time()
out = tr.translate("The quick brown fox jumps over the lazy dog.", "en")
print(f"[en->zh] {out}  （纯推理 {time.time() - t0:.1f}s）")
