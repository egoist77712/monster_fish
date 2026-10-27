```javascript
/* 展台上的 11 屏文案 —— 全部照客户 PDF 原文,连换行都是手写好的。
 *
 * 数据来源:Section 1_Interactive_MinnowOrMonster_TVPrompts.pdf
 * 11 屏 = 1 屏待机 + 10 屏结果
 * (4 条鱼 × "almost / same" 两屏 + baby + beyond)
 *
 * 鱼按体重升序排列，用来决定显示哪一屏。
 * 文案保持原样，仅修改重量判断逻辑。
 */

window.PROMPTS = (() => {
  'use strict';

  // =========================================================
  // 1. 鱼类体重资料：保持原样
  // =========================================================

  const FISH = [
    {
      num: 1,
      key: 'goonch',
      name: 'goonch',
      scientific: 'Bagarius bagarius',
      kg: 75,
      image: 'images/fish/goonch.png',
      almost: 'You are almost as heavy as\nthe largest recorded goonch\n'
              + '(Bagarius bagarius).',
      sameHeadline: 'EXCELLENT!',
      same: 'You weigh the same as the\nlargest recorded goonch\n'
            + '(Bagarius bagarius).',
    },
    {
      num: 2,
      key: 'american-paddlefish',
      name: 'American paddlefish',
      scientific: 'Polyodon spathula',
      kg: 100,
      image: 'images/fish/american-paddlefish.png',
      almost: 'You are almost as heavy\nas the largest recorded\n'
              + 'American paddlefish\n(Polyodon spathula).',
      sameHeadline: 'AMAZING!',
      same: 'You weigh the same as\nthe largest recorded\n'
            + 'American paddlefish\n(Polyodon spathula).',
    },
    {
      num: 3,
      key: 'arapaima',
      name: 'arapaima',
      scientific: 'Arapaima gigas',
      kg: 200,
      image: 'images/fish/arapaima.png',
      almost: 'You are almost as heavy as\nthe largest recorded\n'
              + 'arapaima (Arapaima gigas).',
      sameHeadline: 'OUTSTANDING!',
      same: 'You weigh the same as\nthe largest recorded\n'
            + 'arapaima (Arapaima gigas).',
    },
    {
      num: 4,
      key: 'giant-barb',
      name: 'giant barb',
      scientific: 'Catlocarpio siamensis',
      kg: 300,
      image: 'images/fish/giant-barb.png',
      almost: 'You are almost as heavy as the\nlargest recorded giant barb\n'
              + '(Catlocarpio siamensis).',
      sameHeadline: 'SUPERB!',
      same: 'You weigh exactly the same as\nthe largest recorded giant barb\n'
            + '(Catlocarpio siamensis).',
    },
  ];

  // =========================================================
  // 2. 待机页面：保持原样
  // =========================================================

  const IDLE = {
    band: 'idle',
    headline: 'ARE\nYOU A\nMONSTER\nFISH?',
    text: 'Step up on the scale and\npush the button.',
    extra: null,
    image: null,
    emphasis: [],
  };

  // =========================================================
  // 3. BABY 页面：文案保持原样
  // =========================================================

  const BABY = {
    band: 'baby',
    headline: null,
    text: 'Awww\u2026. Just a\nsmall baby fish.',
    extra: 'Hint: Grab some friends\nand try again.',
    image: null,
    emphasis: [],
  };

  // =========================================================
  // 4. BEYOND 页面：文案保持原样
  // =========================================================

  const BEYOND = {
    band: 'beyond',
    headline: 'OUT OF THIS WORLD!',
    text: 'We have yet to\ncatch and record\na freshwater fish\n'
          + 'that weighs heavier\nthan 300 kg.',
    extra: 'The largest ever recorded\nfreshwater fish was a\n'
           + 'giant freshwater stingray\n(Urogymnus polylepis)\ncaught in 2022.',
    image: null,
    emphasis: ['Urogymnus polylepis'],
  };

  // =========================================================
  // 5. 重量设置
  // =========================================================

  // 最重的鱼类记录体重
  const MAX_RECORDED_KG = FISH[FISH.length - 1].kg;

  // 0–65 kg 显示 BABY
  const BABY_FISH_KG = 65;

  // =========================================================
  // 6. 重量判断逻辑
  // =========================================================

  function resolve(weightKg) {
    const w = Number(weightKg);

    // 无效重量：返回待机页面
    if (!Number.isFinite(w) || w < 0) {
      return { ...IDLE };
    }

    // 超过 300 kg：显示 BEYOND
    if (w > MAX_RECORDED_KG) {
      return { ...BEYOND };
    }

    // 0–65 kg：显示 BABY
    if (w <= BABY_FISH_KG) {
      return { ...BABY };
    }

    // 从最轻的鱼开始，依次判断
    for (const fish of FISH) {

      // 刚好达到记录体重：显示 SAME
      if (w === fish.kg) {
        return {
          band: 'same',
          headline: fish.sameHeadline,
          text: fish.same,
          extra: null,
          image: fish.image,
          emphasis: [fish.scientific],
        };
      }

      // 重量低于当前鱼的记录体重：显示 ALMOST
      if (w < fish.kg) {
        return {
          band: 'almost',
          headline: null,
          text: fish.almost,
          extra: null,
          image: fish.image,
          emphasis: [fish.scientific],
        };
      }

      // 如果超过当前鱼的记录体重，
      // 继续判断下一条鱼
    }

    // 保险处理
    return { ...BEYOND };
  }

  // =========================================================
  // 7. 导出数据，供 app.js 使用
  // =========================================================

  return {
    FISH,
    IDLE,
    BABY,
    BEYOND,
    MAX_RECORDED_KG,
    BABY_FISH_KG,
    resolve,
  };

})();
```
