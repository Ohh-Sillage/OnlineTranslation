# 能量型 VAD：将连续 PCM 流按静音切分为语音段
import numpy as np

import config


class EnergyVAD:
    def __init__(self):
        self.sample_rate = 16000
        self.frame_ms = 30
        self.frame_len = int(self.sample_rate * self.frame_ms / 1000)
        self.threshold = config.VAD_THRESHOLD
        self.min_speech_frames = int(config.VAD_MIN_SPEECH_S * 1000 / self.frame_ms)
        self.min_silence_frames = int(config.VAD_MIN_SILENCE_S * 1000 / self.frame_ms)
        self.pad_samples = int(config.VAD_PAD_S * self.sample_rate)

        self.buffer = np.zeros(0, dtype=np.float32)  # 未满一帧的残余
        self.tick = 0                                 # 全局累计采样数（时间基准）
        self.pending = None                           # 当前语音段样本
        self.pending_start = 0                        # 语音段起始采样位置
        self.silence = 0                              # 连续静音帧数

    def push(self, pcm):
        """输入一段 PCM（float32, 16kHz），返回切分好的 [(start_s, end_s, pcm)]"""
        self.buffer = np.concatenate([self.buffer, pcm])
        segs = []
        while len(self.buffer) >= self.frame_len:
            frame = self.buffer[:self.frame_len]
            self.buffer = self.buffer[self.frame_len:]
            frame_start = self.tick
            self.tick += self.frame_len

            rms = float(np.sqrt(np.mean(frame ** 2)))
            if rms >= self.threshold:
                if self.pending is None:
                    self.pending = frame.copy()
                    self.pending_start = frame_start
                else:
                    self.pending = np.concatenate([self.pending, frame])
                    # 超过最大段长强制切段：避免连续语音/音乐导致段无限增长、识别过慢
                    if len(self.pending) / self.sample_rate >= config.VAD_MAX_SEGMENT_S:
                        seg = self._finalize_seg()
                        if seg is not None:
                            segs.append(seg)
                self.silence = 0
            else:
                self.silence += 1
                if self.pending is not None and self.silence >= self.min_silence_frames:
                    seg = self._finalize_seg()
                    if seg is not None:
                        segs.append(seg)
        return segs

    def flush(self):
        """连接结束 / 无新数据时，返回未完成的语音段并清空状态"""
        self.buffer = np.zeros(0, dtype=np.float32)
        seg = self._finalize_seg()
        return [seg] if seg is not None else []

    def _finalize_seg(self):
        if self.pending is None:
            self.silence = 0
            return None
        duration = len(self.pending) / self.sample_rate
        seg = self.pending
        self.pending = None
        self.silence = 0
        if duration < self.min_speech_frames * self.frame_ms / 1000:
            return None  # 过短，视为噪声
        # 首尾补零，给 Whisper 留出上下文
        padded = np.concatenate([
            np.zeros(self.pad_samples, dtype=np.float32),
            seg,
            np.zeros(self.pad_samples, dtype=np.float32),
        ])
        start_s = max(0.0, self.pending_start / self.sample_rate - config.VAD_PAD_S)
        end_s = (self.pending_start + len(seg)) / self.sample_rate + config.VAD_PAD_S
        return (start_s, end_s, padded)
