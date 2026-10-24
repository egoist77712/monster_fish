
window.PROMPTS = (() => {
  'use strict';

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
      almostMin: 0,
      sameMin: 37.5,
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
      almostMin: 75,
      sameMin: 85,
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
      almostMin: 100,
      sameMin: 150,
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
      almostMin: 200,
      sameMin: 250,
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

  const MAX_RECORDED_KG = 300;

  function resolve(weightKg) {
    const w = Number(weightKg);

    if (!Number.isFinite(w) || w < 0) {
      return { ...IDLE };
    }

    if (w > MAX_RECORDED_KG) {
      return { ...BEYOND };
    }

    let fish;
    let band;

    if (w < 37.5) {
      fish = FISH[0];
      band = 'almost';
    } else if (w <= 75) {
      fish = FISH[0];
      band = 'same';
    } else if (w < 85) {
      fish = FISH[1];
      band = 'almost';
    } else if (w <= 100) {
      fish = FISH[1];
      band = 'same';
    } else if (w < 150) {
      fish = FISH[2];
      band = 'almost';
    } else if (w <= 200) {
      fish = FISH[2];
      band = 'same';
    } else if (w < 250) {
      fish = FISH[3];
      band = 'almost';
    } else {
      fish = FISH[3];
      band = 'same';
    }

    return {
      band,
      headline: band === 'same' ? fish.sameHeadline : null,
      text: band === 'same' ? fish.same : fish.almost,
      extra: null,
      image: fish.image,
      emphasis: [fish.scientific],
    };
  }

  return {
    FISH,
    IDLE,
    BEYOND,
    MAX_RECORDED_KG,
    resolve,
  };
})();
