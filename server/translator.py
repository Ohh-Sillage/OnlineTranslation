# 翻译封装：抽象接口，微软快通道 + 本地 NLLB 兜底
#   auto (默认) : 微软 Edge 新端点 translatetext（约 1s）→ 失败回落本地 NLLB（离线可靠）
#   nllb        : 纯本地 NLLB-200 模型（离线可用，需 transformers + torch）
#   google_free : 仅 Google 免费接口（国内持续 429，已不入 auto 链）
#   mymemory    : 仅 MyMemory 免费接口（同上）
import threading
import time

import config


class Translator:
    _instance = None

    def __init__(self):
        self.strategy = config.TRANSLATOR
        self._tok = None
        self._model = None
        # RLock: NLLB 加载/推理与接口节流状态串行化（transformers 非线程安全；
        # 懒加载发生在 asyncio.to_thread 工作线程，需防并发重复加载）
        self._nllb_lock = threading.RLock()
        self._ms_last = 0.0            # 上次调用微软端点时刻（节流）
        self._ms_fails = 0             # 微软端点连续失败计数
        self._ms_cooldown_until = 0.0  # 失败冷却截止时间戳

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = Translator()
        return cls._instance

    def _load_nllb(self):
        """首次翻译时在调用线程（to_thread）内加载，不阻塞事件循环"""
        if self._model is not None:
            return
        with self._nllb_lock:
            if self._model is not None:
                return
            try:
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            except ImportError:
                raise RuntimeError(
                    "使用 nllb 翻译需要安装: pip install transformers torch sentencepiece"
                )
            print(f"[TRANS] 加载本地 NLLB 模型 {config.NLLB_MODEL_PATH} ...")
            self._tok = AutoTokenizer.from_pretrained(config.NLLB_MODEL_PATH)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(config.NLLB_MODEL_PATH)
            print("[TRANS] NLLB 模型加载完成")

    def translate(self, text, src_lang="ja"):
        if not text:
            return ""
        if self.strategy == "nllb":
            return self._translate_nllb(text, src_lang)
        if self.strategy == "google_free":
            return self._translate_google(text, src_lang)
        if self.strategy == "mymemory":
            return self._translate_mymemory(text, src_lang)
        # auto：微软 Edge 新端点（约 1s）→ 失败自动回落本地 NLLB（约 4s，离线可靠）
        # 连续失败 3 次冷却 60s 直走 NLLB，避免每句都先等接口超时
        with self._nllb_lock:
            if time.time() < self._ms_cooldown_until:
                return self._translate_nllb(text, src_lang)
            try:
                self._throttle()
                out = self._translate_microsoft(text, src_lang)
                self._ms_fails = 0
                return out
            except Exception as exc:  # noqa: BLE001
                self._ms_fails += 1
                if self._ms_fails >= 3:
                    self._ms_cooldown_until = time.time() + 60
                    self._ms_fails = 0
                    print(f"[TRANS] 微软接口连续失败，冷却 60s 改用本地 NLLB: {exc}")
                return self._translate_nllb(text, src_lang)

    def _src_code(self, src_lang):
        return {"ja": "ja", "en": "en", "auto": "auto"}.get(src_lang, "auto")

    def _throttle(self):
        """微软免费端点节流：相邻请求至少间隔 0.9s，防 429 限流"""
        wait = self._ms_last + 0.9 - time.time()
        if wait > 0:
            time.sleep(wait)
        self._ms_last = time.time()

    # ---- 微软 Edge 翻译新端点（2025 起免认证；旧 api-edge 端点已 401 弃用）----
    def _translate_microsoft(self, text, src_lang):
        import requests

        url = "https://edge.microsoft.com/translate/translatetext"
        src = self._src_code(src_lang)
        params = {"to": "zh-Hans", "api-version": "3.0"}
        if src != "auto":
            params["from"] = src
        headers = {
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
            ),
            "Origin": "https://www.microsoft.com",
            "Referer": "https://www.microsoft.com/",
        }
        resp = requests.post(url, params=params, headers=headers, json=[text], timeout=8)
        resp.raise_for_status()
        data = resp.json()
        return data[0]["translations"][0]["text"].strip()

    # ---- MyMemory 免费接口（无需 key，匿名限流；429 频繁，已不入 auto 链）----
    def _translate_mymemory(self, text, src_lang):
        import requests

        src = self._src_code(src_lang)
        pair = f"{src}|zh-CN" if src != "auto" else "ja|zh-CN"
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text, "langpair": pair}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("responseStatus") != 200:
            raise RuntimeError(f"MyMemory 返回异常: {data.get('responseStatus')}")
        return data["responseData"]["translatedText"].strip()

    # ---- Google 免费接口（国内网络持续 429，已不入 auto 链，仅独立策略可用）----
    def _translate_google(self, text, src_lang):
        import requests

        src_code = self._src_code(src_lang)
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": src_code, "tl": "zh-CN", "dt": "t", "q": text}
        headers = {
            # 模拟浏览器 UA，避免免费接口限流（429）
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://translate.google.com/",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        parts = resp.json()[0]
        return "".join(p[0] for p in parts if p and p[0]).strip()

    # ---- 本地 NLLB-200 模型（懒加载；RLock 保证并发连接下加载/推理串行）----
    def _translate_nllb(self, text, src_lang):
        src_map = {"ja": "jpn_Jpan", "en": "eng_Latn", "auto": "eng_Latn"}
        src_code = src_map.get(src_lang, "eng_Latn")
        with self._nllb_lock:
            self._load_nllb()
            self._tok.src_lang = src_code
            inputs = self._tok(text, return_tensors="pt")
            outputs = self._model.generate(
                **inputs,
                forced_bos_token_id=self._tok.convert_tokens_to_ids("zho_Hans"),
            )
            return self._tok.batch_decode(outputs, skip_special_tokens=True)[0].strip()
