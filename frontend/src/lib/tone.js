/* 논조(tone) 스케일 — 세 시안이 각자 쓰던 규칙을 한곳에 모았다.
   값의 범위는 -1(비판) ~ +1(우호)로 통일한다. */

/** -1~1 값을 0~100% 위치로 */
export const P = (v) => ((v + 1) / 2) * 100;

/** 부호를 붙인 소수 둘째자리 표기 (+0.42 / -0.18) */
export const sg = (v) => (v > 0 ? '+' : '') + v.toFixed(2);

/** 논조 색 (CSS 변수) — 신문·미니멀 계열이 쓰는 3단계 */
export const toneVar = (v) =>
  v > 0.32 ? 'var(--wtw-pos)' : v <= -0.34 ? 'var(--wtw-neg)' : 'var(--wtw-neu)';

/** 논조 한국어 라벨 — 5단계 */
export const toneLabel5 = (v) =>
  v > 0.35 ? '우호' : v > 0.15 ? '다소 우호' : v > -0.15 ? '중립' : v > -0.35 ? '다소 비판' : '비판';

/** 논조 한국어 라벨 — 3단계 (코스모스 계열) */
export const toneLabel3 = (v) => (v > 0.32 ? '긍정' : v <= -0.34 ? '부정' : '중립');

/** 논조 → 연속 RGB. 빨강(부정) ↔ 보라회색(중립) ↔ 파랑(긍정) */
const lerp = (a, b, t) => a + (b - a) * t;
export function toneRGB(s) {
  const NEG = [217, 75, 87];    /* 비판 — 빨강 */
  const MID = [158, 167, 180];  /* 중립 — 회색 */
  const POS = [31, 157, 107];   /* 우호 — 초록 */
  const t = (Math.max(-1, Math.min(1, s)) + 1) / 2;
  const seg = t < 0.5 ? [NEG, MID, t * 2] : [MID, POS, (t - 0.5) * 2];
  return [0, 1, 2].map((i) => Math.round(lerp(seg[0][i], seg[1][i], seg[2])));
}

/** 표본 부족 표시 색.
    빨강–회색–초록 스케일 위에 없는 색이어야 "값이 낮다"가 아니라 "값이 없다"로 읽힌다.
    (코스모스 원본이 빨강–보라–파랑 스케일에서 민트를 고른 것과 같은 이유다.) */
export const NO_SAMPLE = [154, 143, 196];

export const rgbHex = (c) => (c[0] << 16) | (c[1] << 8) | c[2];

/** 관심도 점수 → 색 */
export function interestColor(v) {
  const p = Math.max(0, Math.min(1, (v - 30) / 70));
  return `rgb(${Math.round(13 + p * 88)},${Math.round(92 + p * 32)},${Math.round(184 + p * 40)})`;
}
