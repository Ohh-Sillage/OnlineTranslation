// AudioWorklet：将标签页音频线性插值重采样到 16kHz，输出 Float32 PCM
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // 输入采样率 / 目标采样率
    this.pos = 0; // 输入域中的重采样游标
    this.lastSample = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    const out = [];
    while (this.pos < channel.length) {
      const idx = Math.floor(this.pos);
      const frac = this.pos - idx;
      const s0 = idx < channel.length ? channel[idx] : this.lastSample;
      const s1 = idx + 1 < channel.length ? channel[idx + 1] : s0;
      out.push(s0 + (s1 - s0) * frac);
      this.pos += this.ratio;
    }
    this.pos -= channel.length;
    this.lastSample = channel[channel.length - 1];

    if (out.length > 0) {
      this.port.postMessage(new Float32Array(out));
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
