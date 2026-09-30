# 全局配置（可通过环境变量覆盖，如 OT_MODEL=base）
import os

# 服务监听地址
HOST = "127.0.0.1"
PORT = 8765

# Whisper 模型配置
# 可选: tiny / base / small / medium / large-v3（越大越准越慢，日语建议 >= small）
MODEL_SIZE = os.environ.get("OT_MODEL", "small")
# 可选: cpu / cuda（NVIDIA 显卡可用 cuda；AMD 显卡保持 cpu）
DEVICE = os.environ.get("OT_DEVICE", "cpu")
# cpu 推荐 int8；cuda 推荐 float16
COMPUTE_TYPE = os.environ.get("OT_COMPUTE", "int8")
# 解码策略: 1 = 贪心（实时场景最快，推荐）；2-5 = 束搜索（更准更慢，离线用）
BEAM_SIZE = 1
# ctranslate2 CPU 线程数: 建议设物理核数（本机 6 核）；0 = 自动
ASR_CPU_THREADS = int(os.environ.get("OT_THREADS", "6"))
# ASR 引擎策略: auto（ja→ReazonSpeech 日语专用引擎，其他语言→whisper）/ whisper（始终 whisper）
ASR_ENGINE = os.environ.get("OT_ASR_ENGINE", "auto")

# 本地模型统一存放目录（约定：所有模型下载到此处）
LOCAL_MODELS_DIR = r"C:\Users\Latecomer\Desktop\共享\python_work\八斗\GitHub\BaDou_Homework\杨建国\models"

# 默认源语言（客户端连接时会覆盖）
DEFAULT_LANG = "ja"  # ja / en / auto

# 翻译策略: auto（微软 Edge 新端点→失败回落本地 NLLB，默认）/ nllb（纯本地离线）/ google_free / mymemory
TRANSLATOR = os.environ.get("OT_TRANSLATOR", "auto")
# 本地 NLLB-200 模型目录（需含 config.json，huggingface 缓存 snapshots/master 结构）
NLLB_MODEL_PATH = os.path.join(LOCAL_MODELS_DIR, r"facebook--nllb-200-distilled-600M\snapshots\master")
# ReazonSpeech 日语引擎目录（sherpa-onnx int8，35k 小时 YouTube 日语训练，仅支持 ja）
REAZON_MODEL_DIR = os.path.join(LOCAL_MODELS_DIR, "sherpa-onnx-zipformer-ja-reazonspeech-2024-08-01")

# VAD（语音活动检测）参数
VAD_THRESHOLD = 0.012        # 帧能量阈值（RMS）
VAD_MIN_SPEECH_S = 0.25      # 最短语音段（秒），短于此的语音丢弃
VAD_MIN_SILENCE_S = 0.4      # 静音持续多久切段（秒）：日语停顿短，0.4s 更快出字幕
VAD_MAX_SEGMENT_S = 6        # 最大语音段（秒），超长强制切段（识别耗时≈段长，6s 兼顾实时与语义）
VAD_PAD_S = 0.2              # 段前后补零（秒）
