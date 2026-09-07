/** 목업 파생값을 만드는 결정적 해시. 같은 입력이면 항상 같은 값이 나온다. */
export function hash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 9973;
  return h;
}

export const fmt = (n) => n.toLocaleString('en-US');

/** 받침 유무에 따라 은/는, 이/가를 고른다 */
export const josa = (w, pair) => {
  const ch = w.charCodeAt(w.length - 1);
  const has = ch >= 0xac00 && ch <= 0xd7a3 ? (ch - 0xac00) % 28 > 0 : true;
  return w + (has ? pair[0] : pair[1]);
};

/** 받침에 따라 '로/으로'를 고른다. 받침이 없거나 ㄹ이면 '로'. */
export const josaRo = (w) => {
  const ch = w.charCodeAt(w.length - 1);
  if (ch < 0xac00 || ch > 0xd7a3) return `${w}로`;
  const jong = (ch - 0xac00) % 28;
  return w + (jong === 0 || jong === 8 ? '로' : '으로');
};

/** 경도 최단 경로 — 회전 애니메이션이 지구를 한 바퀴 돌지 않게 한다 */
export const shortLon = (from, to) => from + (((to - from + 540) % 360) - 180);

export const prefersReducedMotion = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
