// Offscreen Document：捕获标签页音频 → 重采样 16kHz PCM → WebSocket 发送到本地服务
// 注意：tabCapture 会接管标签页音频（原声音消失），必须将捕获流回放到扬声器
// 版本指纹：v0.1.2（v0.1.1 修复连接自杀循环+回放+resume+失败清理；v0.1.2 随服务端实时化升级）
console.log('[ot] offscreen v0.1.2 loaded');
const WS_URL = 'ws://127.0.0.1:8765/ws';

let mediaStream = null;
let audioContext = null;
let workletNode = null;
let ws = null;
let wsRetryTimer = null;
let lang = 'ja';
let captureActive = false; // 捕获会话是否激活（激活中才自动重连）

function postStatus(wsConnected, error) {
  chrome.runtime.sendMessage({ type: 'status', wsConnected, error: error || '' }).catch(() => {});
}

function connectWs() {
  // 已有连接（含正在建立/正在关闭）则复用：绝不能 close 正常连接，否则
  // onclose 的重连定时器会每 2 秒杀死新连接，形成“连接→断开→重连”死循环
  if (ws && ws.readyState !== WebSocket.CLOSED) {
    return;
  }
  clearTimeout(wsRetryTimer);
  ws = new WebSocket(WS_URL);
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => {
    console.log('[ot] ws connected');
    postStatus(true);
    ws.send(JSON.stringify({ type: 'config', lang }));
  };
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'subtitle') {
        chrome.runtime.sendMessage({
          type: 'subtitle',
          text: msg.text,
          translated: msg.translated,
          start: msg.start,
          end: msg.end
        }).catch(() => {});
      }
    } catch (err) { /* 忽略非 JSON 消息 */ }
  };
  ws.onclose = (e) => {
    console.log('[ot] ws closed, code=', e.code, 'reason=', e.reason, 'captureActive=', captureActive);
    postStatus(false);
    // 仅当捕获会话激活时才自动重连（否则重连无意义，形成死循环）
    if (captureActive) {
      wsRetryTimer = setTimeout(connectWs, 2000);
    }
  };
  ws.onerror = (e) => {
    console.error('[ot] ws error:', e);
    try { ws.close(); } catch (err) { /* ignore */ }
  };
}

// 接收 background 指令
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'capture-start') {
    lang = msg.lang || 'ja';
    // 已在捕获时先清理旧的，防止重复 start 产生双份音频/连接
    if (mediaStream || workletNode) {
      console.log('[ot] already capturing, restart capture');
      stopCapture();
    }
    connectWs();
    startCapture(msg.streamId)
      .then(() => sendResponse({ ok: true }))
      .catch((err) => {
        console.error('[ot] capture failed:', err);
        stopCapture(); // 清理资源，避免声音被吞且无字幕
        postStatus(false, String(err));
        sendResponse({ ok: false, error: String(err) });
      });
    return true;
  }
  if (msg.type === 'capture-stop') {
    stopCapture();
    sendResponse({ ok: true });
    return true;
  }
});

async function startCapture(streamId) {
  // 通过 getMediaStreamId 获取的流 ID 获取标签页音频
  console.log('[ot] getUserMedia, streamId=', streamId.slice(0, 12) + '...');
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } },
    video: false
  });
  console.log('[ot] getUserMedia ok, tracks=', mediaStream.getAudioTracks().length);

  audioContext = new AudioContext();
  // offscreen 无用户手势，AudioContext 可能处于 suspended，必须 resume 才能驱动 worklet
  if (audioContext.state === 'suspended') {
    console.log('[ot] AudioContext suspended, resuming...');
    await audioContext.resume();
  }
  console.log('[ot] AudioContext state=', audioContext.state, 'rate=', audioContext.sampleRate);

  await audioContext.audioWorklet.addModule('audio-worklet.js');
  console.log('[ot] audio-worklet loaded');

  const source = audioContext.createMediaStreamSource(mediaStream);

  // 关键：将捕获的音频回放到扬声器（否则视频原声消失）
  source.connect(audioContext.destination);

  workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');
  workletNode.port.onmessage = (e) => {
    // e.data 为 Float32Array（16kHz 单声道 PCM）
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data);
  };
  source.connect(workletNode);
  workletNode.connect(audioContext.destination); // worklet 输出静音，仅驱动处理循环

  console.log('[ot] capture started, sending PCM');
  captureActive = true;
  postStatus(ws && ws.readyState === WebSocket.OPEN);
}

function stopCapture() {
  captureActive = false;
  clearTimeout(wsRetryTimer); // 主动停止时不再自动重连
  try { if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop()); } catch (e) { /* ignore */ }
  try { if (audioContext) audioContext.close(); } catch (e) { /* ignore */ }
  try { if (ws) ws.close(); } catch (e) { /* ignore */ }
  mediaStream = null;
  audioContext = null;
  workletNode = null;
}
