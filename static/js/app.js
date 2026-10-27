
/*
 * Minnow or Monster - 前端事件驱动版本
 *
 * 不再定时轮询 /api/capture 和 /api/weight。
 *
 * GET  /api/events  建立 SSE 事件连接
 * POST /api/stop    超时后停止称重
 *
 * 后端推送的事件：
 * session_start -> 实体按钮启动称重
 * weight        -> 新的重量数据
 * session_end   -> 称重结束
 * status        -> 连接建立时的当前会话状态
 */

(() => {
  'use strict';

  // ==================================================
  // 1. 配置
  // ==================================================

  const EMPTY_KG = 5;

  // LED 动画最短等待时间
  const LED_ANIMATION_MS = 2600;

  // 最长等待时间
  const LED_ANIMATION_MAX_MS = 8000;

  // 等待动画淡出时间
  const WAIT_FADE_OUT_MS = 240;

  // 会话总时长：2 分钟
  const SESSION_TIMEOUT_MS = 120000;

  // 重量稳定判断
  const STABLE_THRESHOLD_KG = 0.2;
  const STABLE_DURATION_MS = 1000;

  const API = {
    events: '/api/events',
    stop: '/api/stop'
  };

  // ==================================================
  // 2. 获取页面元素
  // ==================================================

  const $ = (id) => document.getElementById(id);

  const el = {
    screen: $('screen'),
    fish: $('fish'),
    headline: $('headline'),
    text: $('text'),
    extra: $('extra'),
    waiting: $('waiting')
  };

  if (Object.values(el).some((node) => !node)) {
    console.error(
      '前端初始化失败：请检查 index.html 中的 screen、fish、headline、text、extra、waiting 元素。'
    );
    return;
  }

  if (!window.PROMPTS || typeof window.PROMPTS.resolve !== 'function') {
    console.error('前端初始化失败：PROMPTS 或 resolve() 不存在。');
    return;
  }

  // ==================================================
  // 3. 前端状态
  // ==================================================

  let phase = 'idle'; // idle | waiting | result

  let lastKey = '';

  let waitStart = 0;
  let sessionStartTime = 0;

  let pendingKg = null;

  let lastSeq = -1;

  let lastObservedKg = null;
  let lastWeightChangeTime = 0;

  let waitHideTimer = null;
  let timeoutTimer = null;

  let timeoutStopSent = false;

  let eventSource = null;

  const FLOW_BANDS = ['almost', 'same', 'beyond'];

  // ==================================================
  // 4. 安全处理文字
  // ==================================================

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
        new RegExp(`(${safe})`, 'g'),
        '<em>$1</em>'
      );
    });

    return html;
  }

  // ==================================================
  // 5. 页面淡入动画
  // ==================================================

  function animateIn(nodes) {
    nodes.forEach((node) => {
      if (!node || node.hidden) return;

      node.style.animation = 'none';

      void node.offsetWidth;

      node.style.animation = '';
    });
  }

  // ==================================================
  // 6. 隐藏等待动画
  // ==================================================

  function fadeOutWaiting() {
    if (el.waiting.hidden) return;

    if (el.waiting.classList.contains('leaving')) return;

    el.waiting.classList.add('leaving');

    clearTimeout(waitHideTimer);

    waitHideTimer = setTimeout(() => {
      el.waiting.hidden = true;
      el.waiting.classList.remove('leaving');
    }, WAIT_FADE_OUT_MS);
  }

  // ==================================================
  // 7. 绘制页面
  // ==================================================

  function paint(prompt) {
    const p = prompt || window.PROMPTS.IDLE;
    const band = p.band || 'idle';

    fadeOutWaiting();

    const key = [
      band,
      p.headline,
      p.text,
      p.extra,
      p.image,
      JSON.stringify(p.emphasis || [])
    ].join('|');

    // 页面内容没有变化时，不重复渲染
    if (key === lastKey) return;

    lastKey = key;

    el.screen.dataset.phase =
      band === 'idle' ? 'idle' : 'result';

    el.screen.dataset.band = band;

    el.screen.dataset.layout =
      FLOW_BANDS.includes(band) ? 'flow' : 'abs';

    // 鱼类图片
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

    animateIn([
      el.fish,
      el.headline,
      el.text,
      el.extra
    ]);
  }

  // ==================================================
  // 8. 显示等待动画
  // ==================================================

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

  // ==================================================
  // 9. 清理会话计时器
  // ==================================================

  function clearSessionTimers() {
    clearTimeout(waitHideTimer);
    clearTimeout(timeoutTimer);

    waitHideTimer = null;
    timeoutTimer = null;
  }

  // ==================================================
  // 10. 返回待机页面
  // ==================================================

  function enterIdle() {
    clearSessionTimers();

    phase = 'idle';

    pendingKg = null;

    sessionStartTime = 0;
    waitStart = 0;

    lastSeq = -1;

    lastObservedKg = null;
    lastWeightChangeTime = 0;

    timeoutStopSent = false;

    paint(window.PROMPTS.IDLE);
  }

  // ==================================================
  // 11. 启动会话
  // ==================================================

  function enterWaiting() {
    // 防止重复的 session_start 事件重新启动动画
    if (phase !== 'idle') return;

    phase = 'waiting';

    waitStart = Date.now();
    sessionStartTime = Date.now();

    pendingKg = null;

    lastSeq = -1;

    lastObservedKg = null;
    lastWeightChangeTime = Date.now();

    timeoutStopSent = false;

    showWaiting();

    // 前端超时保护
    timeoutTimer = setTimeout(() => {
      handleTimeout();
    }, SESSION_TIMEOUT_MS);
  }

  // ==================================================
  // 12. 判断重量是否稳定
  // ==================================================

  function isWeightStable(now) {
    if (pendingKg == null || lastObservedKg == null) {
      return false;
    }

    return (
      now - lastWeightChangeTime >= STABLE_DURATION_MS
    );
  }

  // ==================================================
  // 13. 显示称重结果
  // ==================================================

  function enterResult(kg) {
    if (kg == null || !Number.isFinite(Number(kg))) return;

    if (Number(kg) < EMPTY_KG) return;

    phase = 'result';

    paint(window.PROMPTS.resolve(Number(kg)));
  }

  // ==================================================
  // 14. 更新结果页面
  // ==================================================

  function showForWeight(kg) {
    if (kg == null || !Number.isFinite(Number(kg))) return;

    if (Number(kg) < EMPTY_KG) return;

    paint(window.PROMPTS.resolve(Number(kg)));
  }

  // ==================================================
  // 15. 接收重量事件
  // ==================================================

  function handleWeight(data) {
    if (phase === 'idle') return;

    if (data.active === false) {
      enterIdle();
      return;
    }

    const kg = Number(data.kg);

    if (!Number.isFinite(kg) || kg < 0) return;

    // 如果后端提供序号，则忽略重复或过期的数据
    if (Number.isFinite(Number(data.seq))) {
      const seq = Number(data.seq);

      if (seq <= lastSeq) return;

      lastSeq = seq;
    }

    const now = Date.now();

    // 检查重量变化
    if (
      lastObservedKg === null ||
      Math.abs(kg - lastObservedKg) > STABLE_THRESHOLD_KG
    ) {
      lastWeightChangeTime = now;
    }

    lastObservedKg = kg;
    pendingKg = kg;

    // 等待阶段
    if (phase === 'waiting') {
      const elapsed = now - waitStart;

      const stable = isWeightStable(now);

      const lightsDone =
        elapsed >= LED_ANIMATION_MS &&
        (
          stable ||
          elapsed >= LED_ANIMATION_MAX_MS
        );

      if (!lightsDone) return;

      // 秤上还没有人，继续等待
      if (kg < EMPTY_KG) return;

      enterResult(kg);
      return;
    }

    // 结果阶段：重量变化时才更新页面
    if (phase === 'result') {
      showForWeight(kg);
    }
  }

  // ==================================================
  // 16. 处理超时
  // ==================================================

  function handleTimeout() {
    if (phase === 'idle') return;

    // 先回到待机页面
    enterIdle();

    // 只发送一次停止请求
    if (timeoutStopSent) return;

    timeoutStopSent = true;

    fetch(API.stop, {
      method: 'POST',
      cache: 'no-store'
    }).catch(() => {
      // 请求失败时保持页面待机
    });
  }

  // ==================================================
  // 17. 处理后端事件
  // ==================================================

  function handleSessionEnd() {
    if (phase !== 'idle') {
      enterIdle();
    }
  }

  function handleStatus(data) {
    // 浏览器重新连接 SSE 时，同步当前会话状态
    if (data.active) {
      if (phase === 'idle') {
        enterWaiting();
      }

      if (data.kg != null) {
        handleWeight({
          active: true,
          kg: data.kg,
          seq: data.seq
        });
      }
    } else if (phase !== 'idle') {
      enterIdle();
    }
  }

  // ==================================================
  // 18. 建立 SSE 连接
  // ==================================================

  function connectEvents() {
    if (!('EventSource' in window)) {
      console.error(
        '当前浏览器不支持 SSE，无法接收实时称重事件。'
      );
      return;
    }

    eventSource = new EventSource(API.events);

    // 建立连接时，后端发送当前状态
    eventSource.addEventListener('status', (event) => {
      try {
        handleStatus(JSON.parse(event.data));
      } catch (error) {
        console.error('解析 status 事件失败：', error);
      }
    });

    // 实体按钮启动称重
    eventSource.addEventListener('session_start', (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.active !== false && phase === 'idle') {
          enterWaiting();
        }
      } catch (error) {
        console.error('解析 session_start 事件失败：', error);
      }
    });

    // 新重量到达
    eventSource.addEventListener('weight', (event) => {
      try {
        handleWeight(JSON.parse(event.data));
      } catch (error) {
        console.error('解析 weight 事件失败：', error);
      }
    });

    // 会话结束
    eventSource.addEventListener('session_end', () => {
      handleSessionEnd();
    });

    eventSource.onerror = () => {
      // EventSource 会自动尝试重新连接
      // 不需要使用 setInterval 重复发送 GET 请求
    };
  }

  // ==================================================
  // 19. 初始化
  // ==================================================

  enterIdle();

  // 只建立一个事件连接，不再启动轮询
  connectEvents();

  // 页面关闭时释放连接
  window.addEventListener('pagehide', () => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }

    clearSessionTimers();
  });

})();
