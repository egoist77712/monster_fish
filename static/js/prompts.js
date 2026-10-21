/* 展台上的 11 屏文案 —— 全部照客户 PDF 原文,连换行都是手写好的。
 *
 * 数据来源:Section 1_Interactive_MinnowOrMonster_TVPrompts.pdf
 *   * 11 屏 = 1 屏待机 + 10 屏结果(4 条鱼 × "almost / same" 两屏 + baby + beyond)
 *   * 鱼按体重升序排成阶梯,用来决定"你比哪条鱼重"。
 *
 * 这些文案以前在后端(prompts.py),现在搬到前端:后端只负责给重量,
 * 具体显示哪一屏由前端说了算。
 *
 * 科学名放在 emphasis 里,由 app.js 包成 <em> 以便单独设样式。
 */
window.PROMPTS = (() => {
  'use strict';

  // 体重阶梯(来自客户文档:"Weighing scale interactive discussed on 18092026")
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

  const IDLE = {
    band: 'idle',
    headline: 'ARE\nYOU A\nMONSTER\nFISH?',
    text: 'Step up on the scale and\npush the button.',
    extra: null,
    image: null,
    emphasis: [],
  };

  const BABY = {
    band: 'baby',
    headline: null,
    // 客户 PDF 里是 "Awww" + 省略号 + 句号
    text: 'Awww\u2026. Just a\nsmall baby fish.',
    extra: 'Hint: Grab some friends\nand try again.',
    image: null,
    emphasis: [],
  };

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

  // 最重的一条鱼:超过它就不再有 "same" 档,直接进 "OUT OF THIS WORLD"
  const MAX_RECORDED_KG = FISH[FISH.length - 1].kg;

  // 低于这个体重显示 "small baby fish"(客户文档没给具体数值,这是经验值)
  const BABY_FISH_KG = 20;

  // "一样重"的容差:人体重量会有一两公斤的抖动,不可能要求分毫不差
  const SAME_TOLERANCE = 0.03;

  /**
   * 根据抓取到的重量,决定显示哪一屏。
   *
   * 判定顺序(和客户文档一致):
   *   1. > 300 kg        -> OUT OF THIS WORLD(没有比这更重的记录了)
   *   2. < 20 kg         -> baby fish
   *   3. 落在某条鱼 ±3%  -> "same"(EXCELLENT! / AMAZING! / ...)
   *   4. 否则            -> "almost"(比下一条鱼轻多少)
   */
  function resolve(weightKg) {
    const w = Number(weightKg);

    if (w > MAX_RECORDED_KG) return { ...BEYOND };

    if (w < BABY_FISH_KG) return { ...BABY };

    for (const fish of FISH) {
      if (Math.abs(w - fish.kg) <= fish.kg * SAME_TOLERANCE) {
        return {
          band: 'same',
          headline: fish.sameHeadline,
          text: fish.same,
          extra: null,
          image: fish.image,
          emphasis: [fish.scientific],
        };
      }
    }

    for (const fish of FISH) {
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
    }

    // 理论上走不到这里(300 kg 及以下都被上面覆盖了),保底给 beyond
    return { ...BEYOND };
  }

  return { FISH, IDLE, BABY, BEYOND, MAX_RECORDED_KG, BABY_FISH_KG, SAME_TOLERANCE, resolve };
})();
