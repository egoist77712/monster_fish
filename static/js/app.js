
/*
 * 展台前端：轮询后端，按重量区间切换页面。
 *
 * GET  /api/weight  实时重量 + 稳定状态
 * GET  /api/capture 抓取重量 + 会话状态
 * GET  /api/button  按钮状态（调试 / Postman）
 *
 * 交互流程：
 * 1. 显示主页面。
 * 2. POST /api/button 开始会话，显示 Weighing 等待动画。
 * 3. 灯带动画结束且重量稳定后，切换到结果页。
 * 4. 重量区间变化时，切换到对应结果页。
 * 5. 连续 5 秒低于 5 kg，由后端结束会话并返回主页面。
 * 6. 会话开始后超过 120 秒，自动停止并返回主页面。
 *
 * 页面不显示调试或操作控件。
 */

(() => {
  'use strict';

  // --------------------------------------------------
  // 1. 配置
  // --------------------------------------------------

  const POLL_MS = 120;

  // 低于此重量视为秤上没人
  const EMPTY_KG = 5;

  // 灯带动画最短等待时间
  const LED_ANIMATION_MS = 2600;

  // 重量一直不稳定时的等待上限
  const LED_ANIMATION_MAX_MS = 8000;

  // 等待动画淡出时间
  const WAIT_FADE_OUT_MS = 240;

  // 会话总时长：2 分钟
  const SESSION_TIMEOUT_MS = 120000;

  const API = {
    capture: '/api/capture',
    weight: '/api/weight',
    stop: '/api/stop'
  };

  // --------------------------------------------------
  // 2. 获取页面元素
  // --------------------------------------------------

  const $ = (id) => document.getElementById(id);

  const el = {
    screen: $('screen'),
    fish: $('fish'),
    headline: $('headline'),
    text: $('text'),
    extra: $('extra'),
    waiting: $('waiting')
  };

  // 如果 HTML 缺少必要元素，避免继续执行导致错误
  if (Object.values(el).some((node) => !node)) {
    console.error(
      '前端初始化失败：请检查 index.html 中的 screen、fish、headline、text、extra、waiting 元素。'
    );
    return;
  }

  // --------------------------------------------------
  // 3. 前端状态
  // --------------------------------------------------

  let phase = 'idle'; // idle | waiting | result

  let lastSeq = -1;
  let lastKey = '';

  let waitStart = 0;

  // 当前会话在前端开始计时的时间
  let sessionStartTime = 0;

  let pendingKg = null;

  let waitHideTimer = null;

  // 防止超时后重复发送停止请求
  let timeoutStopSent = false;

  // 这些重量区间使用 flow 布局
  const FLOW_BANDS = ['almost', 'same', 'beyond'];

  // --------------------------------------------------
  // 4. 安全处理文本和强调文字
  // --------------------------------------------------

  function rich(text, emphasis) {
    let html = String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    (emphasis || []).forEach((name) => {
      if (!name) return;

      const safe = String(name).replace(
        /[.*+?^${}()|[\]\\]/g,
        '\\$&'
      );

      html = html.replace(
        new RegExp(`(${safe})`),
        '<em>$1</em>'
      );
    });

    return html;
  }

  // --------------------------------------------------
  // 5. 重新触发淡入动画
  // --------------------------------------------------

  function animateIn(nodes) {
    nodes.forEach((node) => {
      if (!node || node.hidden) return;

      node.style.animation = 'none';

      // 强制浏览器重新计算布局
      void node.offsetWidth;

      // 恢复 CSS 动画
      node.style.animation = '';
    });
  }

  // --------------------------------------------------
  // 6. 等待动画淡出
  // --------------------------------------------------

  function fadeOutWaiting() {
    if (el.waiting.hidden) return;

    // 已经在淡出就不重复执行
    if (el.waiting.classList.contains('leaving')) return;

    el.waiting.classList.add('leaving');

    clearTimeout(waitHideTimer);

    waitHideTimer = setTimeout(() => {
      el.waiting.hidden = true;
      el.waiting.classList.remove('leaving');
    }, WAIT_FADE_OUT_MS);
  }

  // --------------------------------------------------
  // 7. 绘制主页面或结果页面
  // --------------------------------------------------

  function paint(prompt) {
    const p = prompt || window.PROMPTS.IDLE;
    const band = p.band || 'idle';

    // 先淡出等待动画
    fadeOutWaiting();

    const key = [
      band,
      p.headline,
      p.text,
      p.extra,
      p.image,
      JSON.stringify(p.emphasis || [])
    ].join('|');

    // 内容没有变化时不重复重绘
    if (key === lastKey) return;

    lastKey = key;

    el.screen.dataset.phase =
      band === 'idle' ? 'idle' : 'result';

    el.screen.dataset.band = band;

    el.screen.dataset.layout =
      FLOW_BANDS.includes(band) ? 'flow' : 'abs';

    // 鱼图
    if (p.image) {
      el.fish.src = `/static/${p.image}`;
      el.fish.hidden = false;
    } else {
      el.fish.hidden = true;
      el.fish.removeAttribute('src');
    }

    // 标题
    el.headline.textContent = p.headline || '';
    el.headline.hidden = !p.headline;

    // 正文
    el.text.innerHTML = rich(p.text, p.emphasis);
    el.text.hidden = !p.text;

    // 附加文字
    el.extra.innerHTML = rich(p.extra, p.emphasis);
    el.extra.hidden = !p.extra;

    // 新页面淡入
    animateIn([
      el.fish,
      el.headline,
      el.text,
      el.extra
    ]);
  }

  // --------------------------------------------------
  // 8. 显示 Weighing 等待动画
  // --------------------------------------------------

  function showWaiting() {
    el.fish.hidden = true;
    el.fish.removeAttribute('src');

    el.headline.hidden = true;
    el.text.hidden = true;
    el.extra.hidden = true;

    clearTimeout(waitHideTimer);

    el.waiting.classList.remove('leaving');
    el.waiting.hidden = false;

    el.screen.dataset.phase = 'waiting';
    el.screen.dataset.band = 'waiting';
    el.screen.dataset.layout = 'abs';

    lastKey = 'waiting';

    animateIn([el.waiting]);
  }

  // --------------------------------------------------
  // 9. 返回主页面
  // --------------------------------------------------

  function enterIdle() {
    phase = 'idle';

    pendingKg = null;

    sessionStartTime = 0;
    waitStart = 0;

    timeoutStopSent = false;

    paint(null);
  }

  // --------------------------------------------------
  // 10. 开始等待动画
  // --------------------------------------------------

  function enterWaiting() {
    phase = 'waiting';

    waitStart = Date.now();

    // 从检测到新会话时开始计时
    sessionStartTime = Date.now();

    pendingKg = null;

    timeoutStopSent = false;

    showWaiting();
  }

  // --------------------------------------------------
  // 11. 显示结果页
  // --------------------------------------------------

  function enterResult(kg) {
    if (kg == null || kg < EMPTY_KG) return;

    phase = 'result';

    paint(window.PROMPTS.resolve(kg));
  }

  // --------------------------------------------------
  // 12. 根据重量切换结果页
  // --------------------------------------------------

  function showForWeight(kg) {
    if (kg == null || kg < EMPTY_KG) return;

    paint(window.PROMPTS.resolve(kg));
  }

  // --------------------------------------------------
  // 13. 两分钟超时保护
  // --------------------------------------------------

  function handleTimeout() {
    // 立即回到主页面
    enterIdle();

    // 只向后端发送一次停止请求
    if (!timeoutStopSent) {
      timeoutStopSent = true;

      fetch(API.stop, {
        method: 'POST',
        cache: 'no-store'
      }).catch(() => {
        // 请求失败时不显示提示，后端也有自己的超时保护
      });
    }
  }

  // --------------------------------------------------
  // 14. 处理后端数据
  // --------------------------------------------------

  function handle(captureSnap, weightSnap) {
    // 后端会话结束，回到主页面
    if (!captureSnap.active) {
      if (phase !== 'idle') {
        enterIdle();
      }

      return;
    }

    // 前端 120 秒超时保护
    if (
      phase !== 'idle' &&
      sessionStartTime > 0 &&
      Date.now() - sessionStartTime >= SESSION_TIMEOUT_MS
    ) {
      handleTimeout();
      return;
    }

    // 从主页面进入等待动画
    if (phase === 'idle') {
      enterWaiting();
    }

    // 保存最新抓取重量
    if (captureSnap.seq !== lastSeq) {
      lastSeq = captureSnap.seq;
      pendingKg = captureSnap.kg;
    }

    // ----------------------------------------------
    // 等待阶段
    // ----------------------------------------------

    if (phase === 'waiting') {
      const elapsed = Date.now() - waitStart;

      const stable = Boolean(
        weightSnap && weightSnap.stable
      );

      // 至少等够灯带动画时间，并等待重量稳定；
      // 8 秒后作为兜底，不再无限等待稳定状态。
      const lightsDone =
        elapsed >= LED_ANIMATION_MS &&
        (
          stable ||
          elapsed >= LED_ANIMATION_MAX_MS
        );

      if (!lightsDone) return;

      const kg =
        pendingKg != null
          ? pendingKg
          : (weightSnap ? weightSnap.kg : null);

      // 还没有人站上秤，继续等待
      if (kg == null || kg < EMPTY_KG) return;

      enterResult(kg);
      return;
    }

    // ----------------------------------------------
    // 结果阶段
    // ----------------------------------------------

    if (phase === 'result' && pendingKg != null) {
      showForWeight(pendingKg);
    }
  }

  // --------------------------------------------------
  // 15. 获取 JSON
  // --------------------------------------------------

  async function get(url) {
    const response = await fetch(url, {
      cache: 'no-store'
    });

    if (!response.ok) {
      throw new Error(`${url} -> ${response.status}`);
    }

    return response.json();
  }

  // --------------------------------------------------
  // 16. 轮询后端
  // --------------------------------------------------

  async function poll() {
    try {
      const [captureSnap, weightSnap] = await Promise.all([
        get(API.capture),
        get(API.weight)
      ]);

      handle(captureSnap, weightSnap);
    } catch (error) {
      // 网络请求失败时保持现有页面，下一轮继续尝试
      console.warn('轮询失败：', error);
    } finally {
      setTimeout(poll, POLL_MS);
    }
  }

  // --------------------------------------------------
  // 17. 初始化
  // --------------------------------------------------

  enterIdle();

  // 开始轮询
  poll();

})();
