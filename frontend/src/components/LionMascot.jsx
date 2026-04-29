import { useState, useEffect, useCallback } from 'react';

// 8-bit pixel color palette
const C = {
  T: 'transparent',           // transparent
  m: '#E8A838',               // mane gold
  d: '#C07720',               // dark mane
  f: '#FFF3E0',               // face cream
  e: '#3E2723',               // eye dark
  n: '#5D4037',               // nose brown
  r: '#FFB0B0',               // cheek pink
  i: '#D4925A',               // inner ear
};

// 14x12 pixel lion face
const FACE_MAP = [
//  0  1  2  3  4  5  6  7  8  9  10 11 12 13
  ['T','T','T','T','d','m','T','T','d','m','T','T','T','T'],  // 0: mane top
  ['T','T','T','d','m','m','m','d','m','m','m','d','T','T'],  // 1: mane
  ['T','T','d','m','m','m','m','m','m','m','m','m','d','T'],  // 2: mane
  ['T','d','m','i','i','m','m','m','m','i','i','m','m','d'],  // 3: ears
  ['d','m','i','f','f','i','m','d','m','i','f','f','i','m'],  // 4: ears+face
  ['m','m','m','f','f','f','f','m','f','f','f','f','m','m'],  // 5: forehead
  ['m','m','m','f','e','f','f','m','f','f','e','f','m','m'],  // 6: eyes
  ['m','m','m','f','f','f','f','m','f','f','f','f','m','m'],  // 7: forehead
  ['m','m','m','f','r','f','f','m','f','f','r','f','m','m'],  // 8: cheeks
  ['m','m','m','f','f','f','f','m','f','f','f','f','m','m'],  // 9: mid-face
  ['m','m','m','f','f','n','f','m','f','f','n','f','m','m'],  // 10: nose
  ['d','m','m','m','f','f','f','m','f','f','f','m','m','d'],  // 11: mouth
];

// Expression maps (override eye/mouth area)
const EXPRESSION_MAPS = {
  happy: [
    // row 11: smile (pixels 4-9, override with mouth line)
    { r: 11, c: 5, v: 'e' },
    { r: 11, c: 6, v: 'e' },
    { r: 11, c: 7, v: 'e' },
    { r: 11, c: 8, v: 'e' },
  ],
  love: [
    { r: 6, c: 4, v: 'f' }, { r: 6, c: 5, v: 'T' }, // heart eyes
    { r: 6, c: 8, v: 'f' }, { r: 6, c: 9, v: 'T' },
    { r: 5, c: 4, v: 'r' }, { r: 5, c: 9, v: 'r' },
    { r: 7, c: 4, v: 'r' }, { r: 7, c: 9, v: 'r' },
  ],
  surprise: [
    { r: 6, c: 4, v: 'T' }, { r: 6, c: 5, v: 'e' }, // wide eyes
    { r: 6, c: 8, v: 'T' }, { r: 6, c: 9, v: 'e' },
    { r: 10, c: 5, v: 'T' }, { r: 10, c: 8, v: 'T' }, // open mouth
    { r: 10, c: 6, v: 'e' }, { r: 10, c: 7, v: 'e' },
  ],
  wink: [
    { r: 6, c: 4, v: 'T' }, { r: 6, c: 5, v: 'e' }, // left eye open
    { r: 6, c: 8, v: 'T' }, { r: 6, c: 9, v: 'T' }, // right eye closed
    { r: 5, c: 8, v: 'm' }, { r: 6, c: 8, v: 'm' }, { r: 7, c: 8, v: 'm' },
  ],
  sleep: [
    { r: 6, c: 4, v: 'T' }, { r: 6, c: 5, v: 'T' }, // closed eyes
    { r: 6, c: 8, v: 'T' }, { r: 6, c: 9, v: 'T' },
    { r: 6, c: 4, v: 'm' }, { r: 6, c: 5, v: 'm' },
    { r: 6, c: 8, v: 'm' }, { r: 6, c: 9, v: 'm' },
    // zzz
    { r: 2, c: 1, v: 'r' }, { r: 1, c: 0, v: 'r' },
    { r: 0, c: 0, v: 'T' }, { r: 1, c: 1, v: 'T' }, { r: 2, c: 0, v: 'T' },
  ],
};

const EXPRESSION_MESSAGES = {
  happy: '你好呀~',
  love: '喜欢你！',
  surprise: '哇哦！',
  wink: '嘿嘿~',
  sleep: 'zzZ...',
};

const PIXEL_SIZE = 5; // px per pixel cell

export default function LionMascot() {
  const [expr, setExpr] = useState('happy');
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [showMessage, setShowMessage] = useState(false);
  const [facingRight, setFacingRight] = useState(true);
  const [bouncing, setBouncing] = useState(false);

  // Autonomous walking
  useEffect(() => {
    let timeout;
    const walk = () => {
      // Only move left/up (negative x/y), never off-screen right/down
      const newX = -(Math.random() * 180);  // move 0~180px left into page
      const newY = -(Math.random() * 50);   // move 0~50px up into page
      setFacingRight(Math.random() > 0.5);
      setBouncing(true);
      setPosition({ x: newX, y: newY });
      setTimeout(() => setBouncing(false), 400);

      if (Math.random() < 0.3) {
        setShowMessage(true);
        setTimeout(() => setShowMessage(false), 2000);
      }
      if (Math.random() < 0.2) {
        const keys = Object.keys(EXPRESSION_MAPS);
        const randomKey = keys[Math.floor(Math.random() * (keys.length - 1))];
        setExpr(randomKey);
        setTimeout(() => setExpr('happy'), 3000);
      }
      timeout = setTimeout(walk, 3000 + Math.random() * 4000);
    };
    timeout = setTimeout(walk, 2000);
    return () => clearTimeout(timeout);
  }, [position.x, position.y]);

  const handleClick = useCallback(() => {
    const keys = Object.keys(EXPRESSION_MAPS);
    const currentIdx = keys.indexOf(expr);
    const nextIdx = (currentIdx + 1) % keys.length;
    setExpr(keys[nextIdx]);
    setBouncing(true);
    setTimeout(() => setBouncing(false), 400);
    setShowMessage(true);
    setTimeout(() => setShowMessage(false), 2000);
  }, [expr]);

  // Build pixel map with expression overrides
  const pixels = FACE_MAP.map(row => [...row]);
  const overrides = EXPRESSION_MAPS[expr] || [];
  for (const { r, c, v } of overrides) {
    if (r < pixels.length && c < pixels[0].length) {
      pixels[r][c] = v;
    }
  }

  const width = FACE_MAP[0].length;
  const height = FACE_MAP.length;
  const canvasW = width * PIXEL_SIZE;
  const canvasH = height * PIXEL_SIZE;

  return (
    <div className="fixed bottom-6 right-6 z-50 select-none">
      {showMessage && (
        <div className="absolute -top-12 left-1/2 -translate-x-1/2 bg-ac-card border-2 border-ac-brown-dark rounded px-3 py-1.5 shadow-ac-soft animate-pop-in whitespace-nowrap z-10"
          style={{ imageRendering: 'pixelated', borderStyle: 'solid' }}>
          <span className="text-xs font-bold text-ac-brown-dark tracking-wider"
            style={{ fontFamily: 'monospace', fontSize: '9px', lineHeight: '14px' }}>
            {EXPRESSION_MESSAGES[expr]}
          </span>
        </div>
      )}

      <button
        onClick={handleClick}
        className="cursor-pointer block"
        style={{
          transform: `translate(${position.x}px, ${position.y}px) scaleX(${facingRight ? 1 : -1}) ${bouncing ? 'translateY(-8px)' : ''}`,
          transition: bouncing ? 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)' : 'transform 2.5s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
          imageRendering: 'pixelated',
        }}
        title="点我互动"
      >
        <div style={{
          width: canvasW,
          height: canvasH,
          position: 'relative',
          imageRendering: 'pixelated',
        }}>
          {/* Shadow */}
          <div style={{
            position: 'absolute',
            bottom: -4,
            left: 4,
            width: canvasW - 8,
            height: 4,
            background: 'rgba(0,0,0,0.15)',
          }} />
          {/* Pixel grid */}
          {pixels.map((row, ri) =>
            row.map((color, ci) => (
              <div
                key={`${ri}-${ci}`}
                style={{
                  position: 'absolute',
                  left: ci * PIXEL_SIZE,
                  top: ri * PIXEL_SIZE,
                  width: PIXEL_SIZE,
                  height: PIXEL_SIZE,
                  backgroundColor: C[color] || 'transparent',
                }}
              />
            ))
          )}
        </div>
      </button>
    </div>
  );
}
