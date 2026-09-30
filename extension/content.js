// Content Script v0.2.0：字幕悬浮层
// Shadow DOM 隔离站点样式（页面 CSS 无法侵入）；全屏双挂载 + 自愈；
// 自由拖动 + 锁定按钮；字号/颜色/背景/模式等设置全部实时同步
(() => {
  if (window.__otSubtitleInjected) return;
  window.__otSubtitleInjected = true;
  console.log('[ot] content v0.2.0 injected');

  // ===== 设置默认值（storage.local 平铺键覆盖）=====
  const DEFAULTS = {
    fontSize: 20,      // 译文行字号 px
    origFontSize: 14,  // 原文行字号 px
    showOrig: true,    // 双语模式下显示原文行
    mode: 'dual',      // dual 双语 | trans 仅译文 | orig 仅原文
    color: '#ffffff',  // 文字颜色
    bgOpacity: 0.65,   // 字幕背景黑度 0~1（0 = 无背景）
    stroke: true,      // 文字描边
    locked: true,      // 锁定后字幕层完全穿透、不可拖动（防误触）
    pos: null          // {cx, cy} 中心点百分比；null = 默认底部中央
  };
  const KEYS = Object.keys(DEFAULTS);
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  // ===== Shadow DOM 宿主：普通页面里只有一个空元素 =====
  const host = document.createElement('div');
  host.id = 'ot-subtitle-host';
  // font:0/0 阻断可继承属性漏进 shadow 边界；位置用 left/top 百分比 + 中心锚点
  host.style.cssText =
    'all:initial;position:fixed;left:50%;top:84%;transform:translate(-50%,-50%);' +
    'z-index:2147483647;pointer-events:none;font:0/0 system-ui;';

  const shadow = host.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
  <style>
    .frame {
      position: relative;
      display: flex; flex-direction: column; align-items: center; gap: 4px;
      max-width: 88vw; user-select: none;
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      cursor: grab; touch-action: none;
    }
    .frame.locked { cursor: default; pointer-events: none; } /* 锁定：整层穿透，不挡视频点击 */
    .frame.hidden { display: none; }
    .line {
      display: inline-block; width: fit-content; max-width: 100%;
      padding: 2px 14px; border-radius: 6px;
      text-align: center; white-space: pre-wrap; word-break: break-word;
      line-height: 1.45; box-sizing: border-box;
    }
    .trans { font-weight: 600; }
    .lockbtn {
      position: absolute; top: -12px; right: -6px;
      width: 20px; height: 20px; padding: 0;
      border: 1px solid rgba(255,255,255,.4); border-radius: 50%;
      background: rgba(0,0,0,.6); color: #fff;
      font-family: system-ui, sans-serif; font-size: 11px; line-height: 18px;
      text-align: center; cursor: pointer; pointer-events: auto;
      opacity: .45; transition: opacity .15s;
    }
    .frame:not(.locked):hover .lockbtn { opacity: 1; }
    .lockbtn:hover { opacity: 1 !important; }
  </style>
  <div class="frame hidden locked">
    <div class="line trans"></div>
    <div class="line orig"></div>
    <button class="lockbtn" type="button"></button>
  </div>`;
  const frame = shadow.querySelector('.frame');
  const transEl = shadow.querySelector('.trans');
  const origEl = shadow.querySelector('.orig');
  const lockBtn = shadow.querySelector('.lockbtn');

  // ===== 运行态 =====
  let hideTimer = null;
  let logShown = false;
  let S = { ...DEFAULTS };

  function lineBg() {
    return S.bgOpacity > 0 ? `rgba(0,0,0,${S.bgOpacity})` : 'transparent';
  }

  function applyPos() {
    if (S.pos) {
      host.style.left = S.pos.cx + '%';
      host.style.top = S.pos.cy + '%';
    } else {
      host.style.left = '50%';
      host.style.top = '84%'; // 默认：底部约 1/6 处居中
    }
  }

  function applyStyle() {
    // 译文行
    transEl.style.fontSize = S.fontSize + 'px';
    transEl.style.color = S.color;
    transEl.style.background = lineBg();
    transEl.style.textShadow = S.stroke
      ? '0 1px 2px rgba(0,0,0,.85), 0 0 4px rgba(0,0,0,.7)'
      : 'none';
    // 原文行：同色提亮弱化，突出译文主次
    origEl.style.fontSize = S.origFontSize + 'px';
    origEl.style.color = `color-mix(in srgb, ${S.color} 60%, #fff)`;
    origEl.style.background = lineBg();
    origEl.style.textShadow = S.stroke ? '0 1px 2px rgba(0,0,0,.85)' : 'none';
    origEl.style.display = S.mode === 'dual' && S.showOrig ? '' : 'none';
    // 锁定态
    frame.classList.toggle('locked', S.locked);
    lockBtn.textContent = S.locked ? '\u{1F512}' : '\u{1F513}';
    lockBtn.title = S.locked ? '已锁定：点击解锁后按住字幕可拖动' : '已解锁：点击锁定（防误触）';
    applyPos();
  }

  // ===== 字幕显示：按 start/end 段长对齐停留时间 =====
  function showSubtitle(text, translated, segSeconds) {
    const big = S.mode === 'orig' ? (text || translated || '')
      : (translated || text || '');
    const small = S.mode === 'dual' && S.showOrig ? (text || '') : '';
    if (!big) return;
    transEl.textContent = big;
    origEl.textContent = small;
    frame.classList.remove('hidden');
    if (!logShown) {
      logShown = true;
      console.log('[ot] subtitle received:', text, '=>', translated);
    }
    // 段长 2~6 秒对齐；服务端无时间戳时兜底 5 秒
    const dur = segSeconds ? clamp(segSeconds, 2, 6) : 5;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => frame.classList.add('hidden'), dur * 1000);
  }

  // ===== 拖动 + 双击复位（锁定态不触发）=====
  let drag = null;

  frame.addEventListener('pointerdown', (e) => {
    if (S.locked || e.button !== 0 || e.target === lockBtn) return;
    e.preventDefault();
    const r = host.getBoundingClientRect();
    drag = {
      sx: e.clientX, sy: e.clientY,
      cx0: (r.left + r.width / 2) / innerWidth * 100,
      cy0: (r.top + r.height / 2) / innerHeight * 100
    };
    frame.setPointerCapture(e.pointerId);
    frame.style.cursor = 'grabbing';
  });

  frame.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const cx = clamp(drag.cx0 + (e.clientX - drag.sx) / innerWidth * 100, 5, 95);
    const cy = clamp(drag.cy0 + (e.clientY - drag.sy) / innerHeight * 100, 3, 92);
    S.pos = { cx, cy };
    applyPos();
  });

  function endDrag() {
    if (!drag) return;
    drag = null;
    frame.style.cursor = '';
    chrome.storage.local.set({ pos: S.pos }).catch(() => {});
  }
  frame.addEventListener('pointerup', endDrag);
  frame.addEventListener('pointercancel', endDrag);

  frame.addEventListener('dblclick', () => {
    if (S.locked) return;
    S.pos = null;
    applyPos();
    chrome.storage.local.set({ pos: null }).catch(() => {});
  });

  // 锁按钮（stopPropagation 防误触拖动）
  lockBtn.addEventListener('pointerdown', (e) => e.stopPropagation());
  lockBtn.addEventListener('click', () => {
    chrome.storage.local.set({ locked: !S.locked }).catch(() => {});
  });

  // ===== 全屏双挂载 + 自愈 =====
  function attach() {
    const fs = document.fullscreenElement;
    // 站点全屏（播放器容器）会盖住文档层：字幕需挂入；video 元素全屏无法挂载则保持原层
    if (fs && fs !== document.documentElement && !(fs instanceof HTMLVideoElement)) {
      if (host.parentElement !== fs) fs.appendChild(host);
    } else if (host.parentElement !== document.documentElement) {
      document.documentElement.appendChild(host);
    }
  }
  document.addEventListener('fullscreenchange', attach);
  attach(); // 注入时若已处于全屏立即归位
  // YouTube 切清晰度/插广告会重建播放器 DOM，字幕被清后自动重挂
  setInterval(() => {
    if (!host.isConnected) attach();
  }, 4000);

  // ===== 消息与设置同步 =====
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.type !== 'subtitle') return;
    const seg = (typeof msg.start === 'number' && typeof msg.end === 'number')
      ? msg.end - msg.start : null;
    showSubtitle(msg.text || '', msg.translated || '', seg);
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    let dirty = false;
    for (const k of KEYS) {
      if (changes[k]) { S[k] = changes[k].newValue; dirty = true; }
    }
    if (dirty) applyStyle();
  });

  chrome.storage.local.get(KEYS).then((v) => {
    for (const k of KEYS) {
      if (v[k] !== undefined) S[k] = v[k];
    }
    applyStyle();
  });
})();
