// Service Worker：负责创建 offscreen 文档、获取标签页媒体流 ID、转发消息
const OFFSCREEN_URL = 'offscreen.html';

let state = { capturing: false, wsConnected: false, lang: 'ja', targetTabId: null };

// 状态持久化到 session storage：service worker 休眠重启后不丢失，
// 避免 popup 显示“未捕获”而实际 offscreen 仍在捕获 → 重复捕获双份音频
async function loadState() {
  try {
    const saved = await chrome.storage.session.get(['capturing', 'wsConnected', 'lang', 'targetTabId']);
    state = {
      capturing: !!saved.capturing,
      wsConnected: !!saved.wsConnected,
      lang: saved.lang || 'ja',
      targetTabId: saved.targetTabId ?? null
    };
  } catch (e) { /* session storage 不可用时保留内存态 */ }
}

async function saveState() {
  try {
    await chrome.storage.session.set({
      capturing: state.capturing,
      wsConnected: state.wsConnected,
      lang: state.lang,
      targetTabId: state.targetTabId ?? null
    });
  } catch (e) { /* ignore */ }
}

// 确保 offscreen 文档存在（tabCapture 在 MV3 中不能直接用于 service worker）
async function ensureOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
  if (contexts.length === 0) {
    await chrome.offscreen.createDocument({
      url: OFFSCREEN_URL,
      reasons: ['USER_MEDIA'],
      justification: '捕获标签页音频进行实时语音识别与字幕翻译'
    });
  }
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

// 开始捕获（popup 与快捷键共用）：记住目标页、注入字幕层、获取流 ID
async function beginCapture(lang) {
  await loadState();
  await ensureOffscreen();
  const tab = await getActiveTab();
  if (!tab || tab.id == null) return { ok: false, error: '未找到活动标签页' };
  // 主动注入字幕层（幂等）：刷新扩展后无需再手动刷新视频页面
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
  } catch (e) { /* file:// 或商店页等受限页面无法注入，忽略 */ }
  state.capturing = true;
  state.lang = lang || state.lang || 'ja'; // popup 显式传值优先，快捷键沿用上次选择
  state.targetTabId = tab.id; // 记住目标标签页：字幕固定发给它，不依赖当前活动页
  await saveState();
  // 获取标签页音频流 ID（仅能使用一次，需在用户手势链上调用）
  const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
  await chrome.runtime.sendMessage({ type: 'capture-start', streamId, lang: state.lang });
  return { ok: true };
}

async function endCapture() {
  await loadState();
  state.capturing = false;
  await saveState();
  await chrome.runtime.sendMessage({ type: 'capture-stop' });
  return { ok: true };
}

// 处理来自 popup 的指令
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === 'start') {
      sendResponse(await beginCapture(msg.lang));
    } else if (msg.type === 'stop') {
      sendResponse(await endCapture());
    } else if (msg.type === 'getStatus') {
      await loadState();
      sendResponse({ capturing: state.capturing, wsConnected: state.wsConnected, lang: state.lang });
    }
  })();
  return true; // 保持异步响应通道
});

// 快捷键开/停翻译：视频元素全屏（tabCapture 会拦截视频站的全屏按钮）时仍可启动捕获
chrome.commands.onCommand.addListener(async (command) => {
  if (command !== 'toggle-capture') return;
  await loadState();
  if (state.capturing) {
    await endCapture();
  } else {
    const r = await beginCapture();
    console.log('[bg] toggle-capture:', r.ok ? 'started' : 'failed: ' + (r.error || ''));
  }
});

// 转发 offscreen 上报的字幕与状态
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!sender || !sender.url || !sender.url.includes('offscreen.html')) return;
  if (msg.type === 'subtitle') {
    // 固定发给开始翻译时的目标标签页（SW 休眠后内存态丢失，先恢复再发）
    loadState().then(() => {
      const targetId = state.targetTabId;
      if (targetId == null) return;
      chrome.tabs.sendMessage(targetId, msg).catch(() => {});
    });
  } else if (msg.type === 'status') {
    loadState().then(() => {
      state.wsConnected = !!msg.wsConnected;
      saveState();
      chrome.runtime.sendMessage({
        type: 'status',
        wsConnected: state.wsConnected,
        capturing: state.capturing,
        error: msg.error || ''
      }).catch(() => {});
    });
  }
});
