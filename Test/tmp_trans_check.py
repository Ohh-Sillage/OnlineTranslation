# -*- coding: utf-8 -*-
"""翻译快通道冒烟测试：微软 translatetext 端点 + auto 回落（临时脚本，测试后可删除）
运行: python Test\tmp_trans_check.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

import config
from translator import Translator

print("翻译策略:", config.TRANSLATOR)
tr = Translator.instance()

# 1) 直测微软新端点（单独验证请求格式/响应结构，不触发 NLLB 回落）
t0 = time.time()
try:
    out = tr._translate_microsoft("こんにちは。今日はいい天気ですね。", "ja")
    print(f"[微软端点直测] OK ({time.time() - t0:.1f}s): {out}")
except Exception as exc:
    print(f"[微软端点直测] 失败: {exc}")

# 2) auto 全链路（微软优先，失败自动回落本地 NLLB）
t0 = time.time()
out = tr.translate("これはリアルタイム字幕翻訳のテストです。", "ja")
print(f"[auto ja->zh] {out}  ({time.time() - t0:.1f}s)")

t0 = time.time()
out = tr.translate("We need to reduce the subtitle latency.", "en")
print(f"[auto en->zh] {out}  ({time.time() - t0:.1f}s)")
