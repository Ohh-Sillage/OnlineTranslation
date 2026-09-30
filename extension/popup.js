// Popup v0.2.0：控制 + 字幕设置面板
// 所有设置写入 storage.local 平铺键，页面 content script 监听后实时生效
const $ = (id) => document.getElementById(id);
const btn = $('toggle-btn');
const serverStatus = $('server-status');
const wsStatus = $('ws-status');
const preview = $('subtitle-preview');
const pvTrans = preview.querySelector('.pv-trans');
const pvOrig = preview.querySelector('.pv-orig');
const fontSizeEl = $('font-size');
const origFontSizeEl = $('orig-font-size');
const showOrigEl = $('show-orig');
const strokeEl = $('stroke');
const bgOpacityEl = $('bg-opacity');
const lockedEl = $('locked');
const colorSwatches = [...document.querySelectorAll('#color-swatches button')];
const modeButtons = [...document.querySelectorAll('#mode-seg button')];

let capturing = false;

// 当前设置快照（默认与 content.js DEFAULTS 保持一致）
let st = {
  fontSize: 20,
  origFontSize: 14,
  showOrig: true,
  mode: 'dual',
  color: '#ffffff',
  bgOpacity: 0.65,
  stroke: true,
  locked: true
};

// 最近一条真实字幕（预览用；未收到前显示示例文本）
let lastSub = null;
const DEMO = {
  trans: '这是实时字幕翻译的测试。',
  orig: 'これはリアルタイム字幕翻訳のテストです。'
};

async function checkServer() {
  try {
    const r = await fetch('http://127.0.0.1:8765/health', { cache: 'no-store' });
    if (r.ok) {
      serverStatus.textContent = '本地服务正常';
      serverStatus.className = 'badge ok';
    } else {
      throw new Error('bad status');
    }
  } catch (e) {
    serverStatus.textContent = '本地服务未连接';
    serverStatus.className = 'badge bad';
  }
}

async function refreshState() {
  const stt = await chrome.runtime.sendMessage({ type: 'getStatus' });
  capturing = !!stt.capturing;
  btn.textContent = capturing ? '停止翻译' : '开始翻译';
  btn.className = capturing ? 'btn danger' : 'btn primary';
  wsStatus.textContent = stt.wsConnected ? '已连接本地识别服务' : '未连接本地识别服务';
  const radio = document.querySelector(`input[name="lang"][value="${stt.lang}"]`);
  if (radio) radio.checked = true;
}

// ==================== 设置 UI ====================

function renderPreview() {
  // 大行（译文/原文主行）
  const showOrigMode = st.mode === 'orig';
  const trans = lastSub
    ? (showOrigMode ? lastSub.text : lastSub.translated || lastSub.text)
    : (showOrigMode ? DEMO.orig : DEMO.trans);
  pvTrans.textContent = trans;
  pvTrans.style.fontSize = st.fontSize + 'px';
  pvTrans.style.color = st.color;
  pvTrans.style.textShadow = st.stroke ? '0 1px 2px rgba(0,0,0,.85)' : 'none';
  // 小行（原文，仅双语模式显示）
  const dual = st.mode === 'dual' && st.showOrig;
  pvOrig.style.display = dual ? '' : 'none';
  pvOrig.textContent = lastSub ? lastSub.text : DEMO.orig;
  pvOrig.style.fontSize = st.origFontSize + 'px';
  pvOrig.style.background = st.bgOpacity > 0 ? `rgba(0,0,0,${st.bgOpacity})` : 'transparent';
  pvOrig.style.color = `color-mix(in srgb, ${st.color} 60%, #fff)`;
  pvOrig.style.textShadow = st.stroke ? '0 1px 2px rgba(0,0,0,.85)' : 'none';
  preview.style.background = st.bgOpacity > 0 ? `rgba(0,0,0,${st.bgOpacity})` : 'rgba(0,0,0,.12)';
}

function updateControlStates() {
  // 原文相关控件仅双语模式下可用
  const origUsable = st.mode === 'dual' && st.showOrig;
  origFontSizeEl.disabled = !origUsable;
  fontSizeEl.value = st.fontSize;
  $('font-size-val').textContent = st.fontSize;
  origFontSizeEl.value = st.origFontSize;
  $('orig-font-size-val').textContent = st.origFontSize;
  showOrigEl.checked = st.showOrig;
  strokeEl.checked = st.stroke;
  bgOpacityEl.value = Math.round(st.bgOpacity * 100);
  $('bg-opacity-val').textContent = Math.round(st.bgOpacity * 100);
  lockedEl.checked = st.locked;
  modeButtons.forEach((b) => b.classList.toggle('active', b.dataset.mode === st.mode));
  colorSwatches.forEach((b) => b.classList.toggle('active', b.dataset.color === st.color));
}

function syncToStorage(patch) {
  Object.assign(st, patch);
  chrome.storage.local.set(patch).catch(() => {});
  updateControlStates();
  renderPreview();
}

// 控件绑定
fontSizeEl.addEventListener('input', () => syncToStorage({ fontSize: Number(fontSizeEl.value) }));
origFontSizeEl.addEventListener('input', () => syncToStorage({ origFontSize: Number(origFontSizeEl.value) }));
showOrigEl.addEventListener('change', () => syncToStorage({ showOrig: showOrigEl.checked }));
strokeEl.addEventListener('change', () => syncToStorage({ stroke: strokeEl.checked }));
bgOpacityEl.addEventListener('input', () => syncToStorage({ bgOpacity: Number(bgOpacityEl.value) / 100 }));
lockedEl.addEventListener('change', () => syncToStorage({ locked: lockedEl.checked }));
colorSwatches.forEach((b) => b.addEventListener('click', () => syncToStorage({ color: b.dataset.color })));
modeButtons.forEach((b) => b.addEventListener('click', () => syncToStorage({ mode: b.dataset.mode })));
$('reset-pos').addEventListener('click', () => {
  chrome.storage.local.set({ pos: null }).catch(() => {});
  wsStatus.textContent = '字幕位置已复位（页面实时生效）';
  wsStatus.className = 'hint';
});

// 其他端（页面拖拽锁定按钮等）改设置时同步本面板
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;
  let dirty = false;
  for (const k of Object.keys(st)) {
    if (changes[k]) { st[k] = changes[k].newValue; dirty = true; }
  }
  if (changes.pos) dirty = true; // 页面拖动/复位位置不影响面板 UI，仅防止遗漏
  if (dirty) {
    updateControlStates();
    renderPreview();
  }
});

// ==================== 控制 ====================

btn.addEventListener('click', async () => {
  const lang = document.querySelector('input[name="lang"]:checked').value;
  if (capturing) {
    await chrome.runtime.sendMessage({ type: 'stop' });
  } else {
    const res = await chrome.runtime.sendMessage({ type: 'start', lang });
    if (res && res.ok === false) {
      wsStatus.textContent = '启动失败: ' + (res.error || '未知错误');
      wsStatus.className = 'hint error';
      return;
    }
  }
  refreshState();
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'status') {
    wsStatus.className = 'hint';
    if (msg.error) {
      wsStatus.textContent = '错误: ' + msg.error;
      wsStatus.className = 'hint error';
    } else {
      wsStatus.textContent = msg.wsConnected ? '已连接本地识别服务' : '未连接本地识别服务';
    }
  }
  if (msg.type === 'subtitle') {
    lastSub = { text: msg.text, translated: msg.translated };
    renderPreview();
  }
});

(async () => {
  const saved = await chrome.storage.local.get(Object.keys(st));
  Object.assign(st, saved);
  updateControlStates();
  renderPreview();
  checkServer();
  refreshState();
  setInterval(checkServer, 5000);
})();
