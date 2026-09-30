# ASR 封装：多引擎语音识别（懒加载，按语言自动分派）
#   ReazonSpeech（sherpa-onnx，ja 专用）：35k 小时 YouTube 日语训练，int8 RTF≈0.05
#     （官方实测 13.4s 音频识别仅 0.72s），实时性远优于 whisper；输出无标点
#   faster-whisper（多语通用）：ja 之外的语言（en 等），或 OT_ASR_ENGINE=whisper 强制
import os
import threading

import config


class ASR:
    _instance = None

    def __init__(self):
        self._whisper = None
        self._sherpa = None
        self._whisper_lock = threading.Lock()
        self._sherpa_lock = threading.Lock()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ASR()
        return cls._instance

    def _ensure_whisper(self):
        if self._whisper is not None:
            return
        with self._whisper_lock:
            if self._whisper is not None:
                return
            from faster_whisper import WhisperModel

            print(f"[ASR] 加载 whisper {config.MODEL_SIZE} "
                  f"(device={config.DEVICE}, compute_type={config.COMPUTE_TYPE}, "
                  f"threads={config.ASR_CPU_THREADS}) ...")
            self._whisper = WhisperModel(
                config.MODEL_SIZE,
                device=config.DEVICE,
                compute_type=config.COMPUTE_TYPE,
                cpu_threads=config.ASR_CPU_THREADS,  # 显式设物理核数，避免默认线程不足
            )
            print("[ASR] whisper 模型加载完成")

    def _ensure_sherpa(self):
        if self._sherpa is not None:
            return
        with self._sherpa_lock:
            if self._sherpa is not None:
                return
            try:
                import sherpa_onnx
            except ImportError:
                raise RuntimeError(
                    "ReazonSpeech 日语引擎需要: pip install sherpa-onnx "
                    "（或设环境变量 OT_ASR_ENGINE=whisper 回退 whisper）"
                )
            d = config.REAZON_MODEL_DIR
            print(f"[ASR] 加载 ReazonSpeech 日语引擎 (threads={config.ASR_CPU_THREADS}) ...")
            self._sherpa = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=os.path.join(d, "encoder-epoch-99-avg-1.int8.onnx"),
                decoder=os.path.join(d, "decoder-epoch-99-avg-1.onnx"),
                joiner=os.path.join(d, "joiner-epoch-99-avg-1.int8.onnx"),
                tokens=os.path.join(d, "tokens.txt"),
                num_threads=config.ASR_CPU_THREADS,
            )
            print("[ASR] ReazonSpeech 引擎加载完成")

    def transcribe(self, pcm, lang="ja"):
        """识别一段 16kHz float32 PCM，返回文本（可能为空字符串）"""
        # ja → ReazonSpeech 专用引擎（快 5 倍+，实时性关键）；非 ja → faster-whisper
        if lang == "ja" and config.ASR_ENGINE != "whisper":
            return self._transcribe_sherpa(pcm)
        return self._transcribe_whisper(pcm, lang)

    def _transcribe_sherpa(self, pcm):
        self._ensure_sherpa()
        # onnxruntime session 非线程安全：多连接并发时串行（识别本身极快，无感知）
        with self._sherpa_lock:
            stream = self._sherpa.create_stream()
            stream.accept_waveform(16000, pcm)
            self._sherpa.decode_stream(stream)
            return stream.result.text.strip()  # 结果在 stream.result（1.13 API）

    def _transcribe_whisper(self, pcm, lang):
        self._ensure_whisper()
        language = None if lang == "auto" else lang
        segments, _info = self._whisper.transcribe(
            pcm,
            language=language,
            beam_size=config.BEAM_SIZE,
            condition_on_previous_text=False,  # 字幕短段独立解码：省去前文条件重算 + 防漂移
            vad_filter=True,  # 内置 silero VAD，进一步滤噪
        )
        text = "".join(seg.text for seg in segments).strip()
        return text
