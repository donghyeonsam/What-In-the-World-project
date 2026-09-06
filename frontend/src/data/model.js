/* ─────────────────────────────────────────────────────────────
   통합 데이터 모델

   결정표 1번의 결과다.
     1-1  논조 = 스칼라 {s, n}  — s는 -1(부정)~+1(긍정), n은 표본 기사 수
     1-2  분석 대상 7개국       — 코스모스 시안 기준
     1-3  분야 → 테마 → 이슈 3단
     1-4  파생값은 손으로 적지 않고 계산 + 검증한다

   왜 {s, n}인가:
   비율(긍 24% / 중 31% / 부 45%)은 스칼라로 되돌릴 수 없다. 반대는 가능하다.
   그리고 n을 들고 다녀야 "이 값을 믿어도 되는가"를 화면에서 판단할 수 있다.
   ───────────────────────────────────────────────────────────── */

import { hash } from '../lib/format.js';

/* 표본이 이 수보다 적으면 값을 숨기고 '표본 부족'으로 표시한다 */
export const MIN_SAMPLE = 30;

/* ═══════════ 분야 ═══════════ */
export const FIELDS = [
  { id: 'econ', name: '경제' },
  { id: 'tech', name: '산업·기술' },
  { id: 'pol', name: '외교·안보' },
  { id: 'soc', name: '사회·환경' },
];
export const FIELD = (id) => FIELDS.find((f) => f.id === id);
export const FIELD_NAME = (id) => FIELD(id)?.name ?? id;

/* ═══════════ 국가 ═══════════
   m = 수집 매체 수. 매체가 적을수록 "국가의 논조"가 아니라
   "수집 가능한 소수 매체의 논조"일 위험이 커진다 — 편차 경고의 근거. */
export const COUNTRIES = [
  { id: 'kr', name: '한국', en: 'Republic of Korea', flag: '🇰🇷', lat: 36.5, lon: 127.9,
    m: 17, today: 6842, src: '네이버 API + RSS 42개 피드' },
  { id: 'us', name: '미국', en: 'United States', flag: '🇺🇸', lat: 38.9, lon: -95.7,
    m: 24, today: 1240, src: 'GDELT DOC 2.0 · 영어권 매체' },
  { id: 'uk', name: '영국', en: 'United Kingdom', flag: '🇬🇧', lat: 54.0, lon: -2.5,
    m: 18, today: 410, src: 'GDELT · BBC/FT/Guardian 등' },
  { id: 'au', name: '호주', en: 'Australia', flag: '🇦🇺', lat: -25.3, lon: 133.8,
    m: 10, today: 280, src: 'GDELT · ABC/AFR 등' },
  { id: 'me', name: 'UAE·카타르', en: 'UAE & Qatar', flag: '🇦🇪', lat: 24.5, lon: 53.6,
    m: 5, today: 190, src: 'GDELT · Gulf News/Al Jazeera 등' },
  { id: 'af', name: '남아공·케냐', en: 'South Africa & Kenya', flag: '🇿🇦',
    lat: -26.2, lon: 28.0, lat2: -1.3, lon2: 36.8,
    m: 4, today: 150, src: 'GDELT · News24/Nation 등' },
  { id: 'br', name: '브라질', en: 'Brazil', flag: '🇧🇷', lat: -10.3, lon: -53.2,
    m: 6, today: 210, src: 'GDELT · 영문 매체 중심' },
];
export const C = (id) => COUNTRIES.find((c) => c.id === id);
export const C_NAME = (id) => C(id)?.name ?? id;

/* 국가 포커스 시 이슈 핀이 펼쳐질 도시 좌표 */
export const PIN_CITIES = {
  kr: [[37.57, 126.98], [35.18, 129.08], [37.46, 126.7], [36.35, 127.38], [35.87, 128.6]],
  us: [[38.9, -77.04], [40.71, -74.01], [29.76, -95.37], [37.77, -122.42]],
  uk: [[51.51, -0.13], [57.15, -2.09], [53.48, -2.24]],
  au: [[-33.87, 151.21], [-31.95, 115.86], [-37.81, 144.96]],
  me: [[25.2, 55.27], [25.29, 51.53], [24.45, 54.38]],
  af: [[-26.2, 28.05], [-1.29, 36.82], [-33.92, 18.42]],
  br: [[-15.79, -47.88], [-23.55, -46.63], [-22.91, -43.17]],
};

/* 여론 톤 채색용 ISO 코드 매핑 */
export const ISO3 = {
  kr: ['KOR'], us: ['USA'], uk: ['GBR'], au: ['AUS'],
  me: ['ARE', 'QAT'], af: ['ZAF', 'KEN'], br: ['BRA'],
};

/* ═══════════ 테마 ═══════════
   vol(국가별 보도량)과 bars(최근 7일 추이)는 아래에서 이슈로부터 계산한다. */
export const THEMES = [
  { id: 'rate', name: '금리', field: 'econ', mult: '5.2×' },
  { id: 'fx', name: '환율', field: 'econ', mult: '2.4×' },
  { id: 'energy', name: '에너지·LNG', field: 'econ', mult: '3.1×' },
  { id: 'semi', name: '반도체 공급망', field: 'tech', mult: '4.6×' },
  { id: 'ship', name: '조선·수출', field: 'tech', mult: '2.8×' },
  { id: 'war', name: '전쟁·분쟁', field: 'pol', mult: '1.9×' },
  { id: 'trade', name: '통상 규제', field: 'pol', mult: '3.8×' },
  { id: 'climate', name: '기후·탄소', field: 'soc', mult: '1.6×' },
  { id: 'resource', name: '원자재·농산물', field: 'soc', mult: '1.4×' },
  { id: 'labor', name: '고용·물가', field: 'soc', mult: '2.1×' },
];
export const T = (id) => THEMES.find((t) => t.id === id);
export const T_NAME = (id) => T(id)?.name ?? id;

/* ═══════════ 이슈 ═══════════
   tone은 [s, n] 쌍으로 적는다 — 아래에서 {s, n} 객체로 편다.
   delta는 직전 기간 대비 기사량 증가율(%), momentum은 평시 논조 대비 이동폭. */
const RAW_ISSUES = [
  { id: 'fed', theme: 'rate', title: '미 연준 금리 인상 가능성 시사',
    summary: '복수의 연준 위원이 인플레이션 둔화가 확인될 때까지 인하를 서두르지 않겠다는 입장을 밝혔다. 시장 기대와의 괴리가 커지고 있다.',
    delta: 183, momentum: -0.14,
    tone: { us: [-0.35, 512], kr: [-0.42, 228], uk: [-0.28, 190], au: [-0.15, 84], br: [-0.30, 66], me: [0.05, 22], af: [0, 8] } },

  { id: 'rate-hike', theme: 'rate', title: '기준금리 인상 기조 재부각',
    summary: '고용 지표가 예상을 웃돌면서 금리 경로 재평가가 이어졌다. 통화 방어선이 걸린 나라일수록 논조가 날카롭다.',
    delta: 121, momentum: -0.11,
    tone: { kr: [-0.42, 196], us: [-0.35, 441], uk: [-0.28, 163], au: [-0.15, 72], me: [0.05, 19], af: [0, 7], br: [-0.30, 58] } },

  { id: 'yen', theme: 'fx', title: '일본 엔화 약세 지속',
    summary: '엔 약세가 이어지며 아시아 통화 전반에 압력이 번졌다. 한국 매체는 수출 경쟁력 관점에서, 영미권은 캐리 트레이드 관점에서 썼다.',
    delta: 94, momentum: -0.06,
    tone: { kr: [-0.24, 174], us: [-0.08, 96], uk: [-0.04, 54], au: [0.02, 28], me: [0.01, 11], af: [0, 5], br: [-0.05, 17] } },

  { id: 'lng', theme: 'energy', title: '카타르 LNG 발주 확대',
    summary: '카타르에너지가 아시아 구매자들과 20년 장기 공급 계약을 추가 체결했다. 발주를 받는 쪽과 값을 치르는 쪽의 논조가 반대로 움직였다.',
    delta: 147, momentum: 0.18,
    tone: { kr: [0.72, 147], me: [0.65, 118], us: [0.10, 64], uk: [-0.05, 38], au: [0.25, 31], br: [0.20, 11], af: [0, 6] } },

  { id: 'oil', theme: 'energy', title: '중동 긴장에 원유 가격 급등',
    summary: '호르무즈 해협 인근 긴장으로 브렌트유가 장중 3% 넘게 올랐다. 산유국과 수입국의 논조가 정확히 갈렸다.',
    delta: 94, momentum: -0.09,
    tone: { kr: [-0.37, 158], us: [-0.18, 204], uk: [-0.21, 121], au: [-0.09, 63], me: [0.46, 142], af: [-0.12, 26], br: [0.18, 49] } },

  { id: 'semi-ctl', theme: 'semi', title: 'AI 반도체 수출 규제 확대',
    summary: '미 상무부가 규제 품목을 재조정했다. 허가를 내주는 쪽과 받아야 하는 쪽의 논조가 반대로 움직였다.',
    delta: 210, momentum: -0.16,
    tone: { kr: [-0.38, 302], us: [0.22, 276], uk: [-0.05, 88], au: [-0.10, 35], br: [0, 14], me: [0, 9], af: [0, 4] } },

  { id: 'semi-kr', theme: 'semi', title: '한국 반도체 수출 5개월 연속 증가',
    summary: 'HBM 등 고부가 메모리 수요가 실적을 견인했다. 국내 매체는 강한 우호, 경쟁국 매체는 중립에 가깝다.',
    delta: 147, momentum: 0.21,
    tone: { kr: [0.72, 341], us: [0.18, 112], uk: [0.04, 47], au: [0.08, 22], me: [0.02, 8], af: [-0.04, 3], br: [0.03, 9] } },

  { id: 'ship-order', theme: 'ship', title: '한국 조선업 LNG선 수주 급증',
    summary: '카타르발 추가 발주로 국내 조선 3사 수주 잔량이 3년 만에 최대치를 기록했다. 중동 에너지 이슈와 맞물려 움직인다.',
    delta: 680, momentum: 0.24,
    tone: { kr: [0.68, 214], us: [0.11, 58], uk: [0.04, 31], au: [0.08, 17], me: [0.53, 96], af: [0.02, 4], br: [0.06, 12] } },

  { id: 'ukr', theme: 'war', title: '러시아-우크라이나 전쟁 공습 확대',
    summary: '민간 시설 피해가 보고되며 서방권 보도가 급증했다. 모든 나라가 부정 쪽에 몰린 드문 사례다.',
    delta: 88, momentum: -0.31,
    tone: { us: [-0.82, 487], uk: [-0.78, 391], kr: [-0.55, 142], au: [-0.62, 118], me: [-0.12, 96], br: [-0.18, 41], af: [0.08, 12] } },

  { id: 'tariff', theme: 'trade', title: '전기차 관세 상호 인상',
    summary: '관세가 상호 인상되어 즉시 발효됐다. 생산기지를 가진 나라와 수출로 먹고사는 나라의 논조가 갈렸다.',
    delta: 156, momentum: 0.13,
    tone: { kr: [-0.08, 163], us: [0.42, 288], uk: [0.16, 74], au: [-0.04, 29], me: [0.02, 12], af: [-0.06, 7], br: [0.34, 86] } },

  { id: 'cop', theme: 'climate', title: 'COP 공동선언, 화석연료 감축안 채택',
    summary: '감축 시한을 두고 막판까지 공방이 이어졌다. 자원 수출 비중이 큰 나라일수록 비판이 강하다.',
    delta: 89, momentum: 0.08,
    tone: { kr: [-0.12, 88], us: [0.20, 196], uk: [0.34, 152], au: [-0.22, 71], me: [-0.28, 44], af: [0.26, 38], br: [-0.18, 94] } },

  { id: 'mineral', theme: 'resource', title: '핵심 광물 수출 규제 논의 착수',
    summary: '주요 광물의 부가가치 수출 정책 논의가 시작됐다. 배터리 공급망과 얽혀 교차 보도가 늘고 있다.',
    delta: 112, momentum: 0.16,
    tone: { kr: [-0.16, 74], us: [-0.10, 131], uk: [-0.06, 48], au: [0.38, 102], me: [0.04, 9], af: [0.44, 66], br: [0.12, 27] } },

  { id: 'jobs', theme: 'labor', title: '미 고용지표 예상치 상회',
    summary: '비농업 고용이 예상을 웃돌며 노동시장 과열 우려가 재점화됐다. 금리 이슈와 강하게 연동된다.',
    delta: 76, momentum: 0.09,
    tone: { us: [0.31, 245], kr: [-0.06, 58], uk: [0.12, 63], au: [0.09, 24], me: [0.01, 6], af: [0, 3], br: [-0.02, 11] } },
];

/* [s, n] → {s, n} 으로 펴고, 총 기사 수를 표본 합으로 계산한다 */
export const ISSUES = RAW_ISSUES.map((raw) => {
  const tone = {};
  Object.entries(raw.tone).forEach(([cid, [s, n]]) => {
    tone[cid] = { s, n };
  });
  return {
    ...raw,
    tone,
    n: Object.values(tone).reduce((sum, d) => sum + d.n, 0),
    spark: sparkPath(raw.id),
  };
});
export const I = (id) => ISSUES.find((x) => x.id === id);

/* ═══════════ 기사 ═══════════
   cat(원본 카테고리)은 themeId로 정규화해 두었다.
   tr은 신뢰도 점수(0~100)로 지구본 핀 색에 쓰인다. */
const RAW_ARTICLES = [
  ['kr', 'semi', '반도체 수출 5개월 연속 증가… HBM 수요 견인', '연합뉴스', 14, 88, 284,
    '6월 반도체 수출이 전년 대비 21% 증가하며 5개월 연속 상승세를 이어갔다. HBM 등 고부가 메모리 수요가 전체 실적을 견인한 것으로 분석된다.'],
  ['kr', 'ship', '한국 조선업 수주 급증, LNG선 발주 재개 영향', '한국경제', 31, 82, 452,
    '카타르발 LNG 운반선 추가 발주가 재개되면서 국내 조선 3사의 수주 잔량이 3년 만에 최대치를 기록했다.'],
  ['kr', 'rate', '기준금리 동결 전망 우세… 환율 변동성은 확대', '매일경제', 47, 76, 198,
    '미 연준의 금리 인상 가능성이 재부각되며 원/달러 환율 변동성이 커졌다. 시장은 한은의 기준금리 동결을 유력하게 보고 있다.'],
  ['kr', 'semi', '"충격" 반도체 관련주 개미들 몰렸다… 실상은', 'OO투데이', 52, 34, 12,
    '제목과 달리 본문은 일반적인 수급 동향 기사로, 자극적 표현 대비 정보량이 낮다고 판단됨. 교차 보도 12건으로 확산성도 낮은 편.'],
  ['kr', 'trade', '정부, 첨단산업 세액공제 연장안 발표', 'KBS', 73, 85, 167,
    '반도체·이차전지 등 국가전략기술 투자 세액공제를 2029년까지 연장하는 개정안이 발표됐다.'],
  ['kr', 'fx', '원/달러 1,340원대 진입… 수입 물가 비상', '서울경제', 58, 80, 143,
    '환율 상승분이 수입 원자재 가격에 반영되며 하반기 물가 전망이 상향 조정되고 있다.'],

  ['us', 'rate', '연준 위원들, 금리 인하 시기 늦춰질 가능성 시사', 'Reuters', 9, 91, 312,
    '복수의 연준 위원이 인플레이션 지표 둔화가 확인될 때까지 금리 인하를 서두르지 않겠다는 입장을 밝혔다.'],
  ['us', 'labor', '미 6월 고용지표 예상치 상회… 노동시장 견조', 'AP', 26, 89, 245,
    '비농업 고용이 예상치를 웃돌며 노동시장 과열 우려가 재점화됐다. 금리 경로 재평가로 국채 금리가 상승했다.'],
  ['us', 'energy', '셰일 업계, 유가 급등에도 증산 신중 모드', 'Bloomberg', 41, 83, 156,
    '중동 긴장에 따른 유가 상승에도 미 셰일 기업들은 주주 환원을 우선하며 증산을 자제하는 분위기다.'],
  ['us', 'semi', 'AI 데이터센터 전력 수요, 전망치 또 상향', 'WSJ', 88, 79, 134,
    'AI 인프라 확대로 미 전력 수요 전망이 재차 상향 조정됐다. 에너지 카테고리와의 교차 이슈로 분류됐다.'],
  ['us', 'war', '민간 시설 피해 보고… 추가 지원 논의 착수', 'AP', 35, 90, 401,
    '공습 피해 규모가 보고되면서 의회 내 추가 지원 논의가 재개됐다.'],

  ['uk', 'rate', '런던 금융시장, 미 금리 이슈에 동조 변동', 'BBC', 18, 86, 176,
    '미 연준발 금리 이슈가 24분 만에 런던 시장으로 전파되며 FTSE 변동성이 확대됐다.'],
  ['uk', 'energy', '북해 유전 신규 탐사 허가 두고 논쟁 가열', 'The Guardian', 64, 81, 98,
    '에너지 안보와 기후 목표 사이에서 북해 신규 탐사 허가를 둘러싼 정치권 공방이 이어지고 있다.'],
  ['uk', 'trade', '유럽 경기 둔화 신호… 영국 수출 전선 영향권', 'Financial Times', 102, 84, 143,
    '유로존 PMI 부진이 이어지며 영국 수출 기업들의 하반기 전망이 하향 조정되고 있다.'],
  ['uk', 'climate', '감축 시한 합의… "이행 점검이 관건"', 'The Guardian', 77, 85, 121,
    '공동선언 채택 이후 이행 점검 체계를 두고 후속 협상이 이어질 전망이다.'],

  ['au', 'resource', '철광석 가격 반등에 광산주 강세', 'AFR', 22, 85, 88,
    '중국 경기 부양책 기대감으로 철광석 선물이 반등하며 호주 주요 광산 기업 주가가 동반 상승했다.'],
  ['au', 'trade', '호-중 무역 관계 개선 흐름… 와인 관세 이후 첫 지표', 'ABC News', 57, 82, 64,
    '관세 철회 이후 대중 수출 회복세가 지표로 확인됐다. 원자재 수요 전망에 긍정 신호로 해석된다.'],
  ['au', 'rate', 'RBA 의사록 공개… 추가 인상 여지 남겨', 'Reuters AU', 95, 87, 71,
    '호주중앙은행이 인플레이션 재상승 시 추가 인상 가능성을 배제하지 않았다.'],

  ['me', 'energy', '중동 긴장 고조로 유가 3% 급등', 'Bloomberg ME', 11, 88, 156,
    '호르무즈 해협 인근 긴장이 고조되며 브렌트유가 장중 3% 넘게 상승했다.'],
  ['me', 'energy', '카타르, 아시아向 LNG 장기 계약 추가 체결', 'Gulf Times', 38, 84, 92,
    '카타르에너지가 아시아 구매자들과 20년 장기 공급 계약을 추가 체결했다. 한국 조선업 수주와 연결되는 흐름이다.'],
  ['me', 'trade', 'UAE, 비석유 부문 성장률 목표 상향', 'The National', 81, 80, 47,
    'UAE 정부가 경제 다각화 전략의 일환으로 비석유 부문 성장 목표를 상향 조정했다.'],

  ['af', 'energy', '남아공 백금 생산 차질… 전력난 재점화', 'News24', 29, 83, 58,
    '에스콤 전력 공급 불안이 재발하며 백금 광산 가동률이 하락했다.'],
  ['af', 'resource', '케냐 커피 경매가 강세… 수출 물량은 감소', 'Daily Nation', 66, 79, 41,
    '품질 등급 상위 물량 부족으로 나이로비 경매 가격이 강세를 보였다.'],
  ['af', 'resource', '희토류·망간 수출 규제 논의 착수', 'Reuters Africa', 110, 81, 66,
    '주요 광물의 부가가치 수출 정책 논의가 시작됐다. 배터리 공급망 관련 교차 보도가 증가하는 추세다.'],

  ['br', 'resource', '브라질 대두 수확 마무리… 수출 물량 사상 최대', 'Reuters Brazil', 16, 87, 104,
    '올해 대두 수확이 마무리 단계에 접어들며 수출 물량이 사상 최대치를 경신할 전망이다.'],
  ['br', 'resource', '커피 산지 서리 우려에 아라비카 선물 급등', 'Bloomberg Línea', 44, 84, 97,
    '미나스제라이스 산지의 한파 예보로 아라비카 선물이 급등했다. 케냐 경매 강세와 맞물려 있다.'],
  ['br', 'energy', '페트로브라스, 심해 유전 신규 투자 계획 발표', 'Valor Int.', 120, 80, 52,
    '프리솔트 심해 유전에 대한 5개년 투자 계획이 발표됐다.'],
  ['br', 'climate', '농축산 수출 타격 우려… 업계 반발', 'Valor Int.', 92, 78, 88,
    '감축안 이행 시 농축산 수출 원가가 오를 수 있다는 업계 분석이 나왔다.'],
];

/* 기사 논조는 별도로 매기지 않고, 그 나라가 그 테마에서 보인 논조를 중심으로 흩뿌린다.
   개별 기사가 국가 대푯값과 똑같을 리 없으므로 결정적 해시로 편차를 준다. */
function articleTone(countryId, themeId, title) {
  const base = themeToneOf(countryId, themeId);
  const jitter = (((hash(title + countryId) % 13) - 6) / 20); /* ±0.30 */
  return Math.max(-1, Math.min(1, +(base + jitter).toFixed(2)));
}

export const ARTICLES = RAW_ARTICLES.map(([country, theme, title, source, minutes, trust, cross, summary], i) => ({
  id: `a${i}`,
  country,
  theme,
  title,
  source,
  minutes,
  trust,
  cross,
  summary,
  s: articleTone(country, theme, title),
}));

/* ═══════════ 파생값 ═══════════
   결정표 1-4: 테마의 값은 손으로 적지 않고 소속 이슈에서 계산한다.
   따로 적으면 "테마엔 잡히는데 이슈가 없는 나라"가 조용히 생긴다. */

/** 국가 c가 테마 t에서 보인 논조 — 소속 이슈들의 표본 가중 평균 */
export function themeToneOf(countryId, themeId) {
  const its = ISSUES.filter((i) => i.theme === themeId);
  let num = 0;
  let den = 0;
  its.forEach((i) => {
    const d = i.tone[countryId];
    if (!d) return;
    num += d.s * d.n;
    den += d.n;
  });
  return den ? num / den : 0;
}

/** 국가 c가 테마 t에서 낸 표본 수 합 */
export function themeSampleOf(countryId, themeId) {
  return ISSUES.filter((i) => i.theme === themeId).reduce(
    (sum, i) => sum + (i.tone[countryId]?.n ?? 0), 0,
  );
}

/** 7일 추이 막대 — 목업. 증가율이 클수록 뒤쪽이 가파르게 오른다. */
function bars7(seed, delta) {
  const h = hash(seed);
  const rise = Math.min(1, delta / 220);
  return Array.from({ length: 7 }, (_, i) => {
    const t = i / 6;
    const base = 18 + t * (30 + rise * 55);
    const wobble = ((h >> (i * 2)) % 11) - 5;
    return Math.max(8, Math.min(100, Math.round(base + wobble)));
  });
}

/** 이슈 카드용 스파크라인 path — 목업. 46×14 좌표계. */
function sparkPath(seed) {
  const h = hash(seed);
  const pts = Array.from({ length: 8 }, (_, i) => {
    const x = 1 + (i * 44) / 7;
    const y = 12 - ((h >> (i * 3)) % 10) - i * 0.35;
    return [x.toFixed(1), Math.max(1, Math.min(13, y)).toFixed(1)];
  });
  return `M${pts[0][0]} ${pts[0][1]} ` + pts.slice(1).map(([x, y]) => `L${x} ${y}`).join(' ');
}

/* 테마에 파생값을 채운다 (import 시 1회) */
THEMES.forEach((t) => {
  const its = ISSUES.filter((i) => i.theme === t.id);
  t.issueCount = its.length;
  t.n = its.reduce((sum, i) => sum + i.n, 0);
  t.delta = Math.round(its.reduce((sum, i) => sum + i.delta, 0) / (its.length || 1));
  t.rise = `+${t.delta}%`;
  t.bars = bars7(t.id, t.delta);
  t.leadingIssue = its.slice().sort((a, b) => b.n - a.n)[0]?.title ?? '';
  /* 국가별 보도량(%) — 지구본과 목록이 같은 근거를 쓰게 한다 */
  t.vol = {};
  COUNTRIES.forEach((c) => {
    const n = themeSampleOf(c.id, t.id);
    if (n) t.vol[c.id] = Math.max(1, Math.round((n / t.n) * 100));
  });
});

/* ═══════════ 국가간 관심도 ═══════════
   절대 기사 수로 계산하면 화살표가 전부 미국을 향하고 매일 같은 그림이 나온다.
   그래서 "겹치는 관심"으로 잰다.

     out(a → b) = Σ_이슈  n_a(이슈) × share_b(이슈)
     share_b(이슈) = b가 그 이슈에 쓴 표본 / b의 전체 표본

   "a가 쓴 양 중, b가 중요하게 보는 주제에 걸린 만큼"이다.
   방향에 따라 값이 달라지므로 '보낸 관심'과 '받은 관심'을 나눠 볼 수 있다.
   이 값도 이슈 표본에서 나오는 파생값이라 데이터를 늘리면 같이 움직인다. */

const TOTAL_N = Object.fromEntries(
  COUNTRIES.map((c) => [c.id, ISSUES.reduce((sum, i) => sum + (i.tone[c.id]?.n ?? 0), 0)]),
);

function rawOut(a, b, issueId = null) {
  if (a === b) return 0;
  const pool = issueId ? ISSUES.filter((i) => i.id === issueId) : ISSUES;
  return pool.reduce((sum, i) => {
    const na = i.tone[a]?.n ?? 0;
    const nb = i.tone[b]?.n ?? 0;
    if (!na || !nb || !TOTAL_N[b]) return sum;
    return sum + na * (nb / TOTAL_N[b]);
  }, 0);
}

/* 0~99로 정규화 — 그 방향에서 가장 큰 값이 99가 된다 */
function normalize(a, direction, issueId) {
  const raws = COUNTRIES.filter((c) => c.id !== a).map((c) => ({
    c,
    raw: direction === 'outgoing' ? rawOut(a, c.id, issueId) : rawOut(c.id, a, issueId),
  }));
  const max = Math.max(...raws.map((r) => r.raw), 1);
  return raws.map((r) => ({ ...r, v: Math.max(6, Math.round((r.raw / max) * 99)) }));
}

/** 두 나라 사이 관심도(방향 있음). 0~99 */
export function interestScore(a, b, direction = 'outgoing', issueId = null) {
  if (a === b) return null;
  return normalize(a, direction, issueId).find((r) => r.c.id === b)?.v ?? 0;
}

/** AttentionPanel이 먹는 모양 — [국기, 국명, 횟수, 막대%, 증감] */
export function attentionRows(countryId, direction, issueId = null) {
  return normalize(countryId, direction, issueId)
    .sort((x, y) => y.v - x.v)
    .map(({ c, raw, v }) => {
      const d = ((hash(countryId + c.id + direction) % 29) - 12) / 10;
      return [c.flag, c.name, `${Math.round(raw).toLocaleString()}회`, v, `${d >= 0 ? '+' : ''}${d.toFixed(1)}%`];
    });
}

/** 관심의 방향이 얼마나 기울었는지 — 인사이트 문장에 쓴다 */
export function attentionLead(countryId, direction, issueId = null) {
  const rows = normalize(countryId, direction, issueId).sort((x, y) => y.v - x.v);
  const total = rows.reduce((sum, r) => sum + r.raw, 0) || 1;
  return { top: rows[0].c, share: ((rows[0].raw / total) * 100).toFixed(1) };
}

/* ═══════════ 편차 · 신뢰도 ═══════════ */

/** 매체 간 논조 편차 — 수집 매체가 적은 나라일수록 좁게 나온다 */
export function spreadOf(issueId, countryId) {
  const c = C(countryId);
  const cap = Math.min(c ? c.m : 3, 20) / 20;
  return +(0.04 + cap * 0.2 + (hash(countryId + issueId) % 5) / 100).toFixed(3);
}

/** 최근 30일 평시 기준선 */
export function baseOf(issueId, countryId) {
  const d = I(issueId)?.tone[countryId];
  if (!d) return 0;
  const move = ((hash(issueId + countryId) % 25) - 12) / 60;
  return Math.max(-1, Math.min(1, d.s - move));
}

/** 표본이 충분한가 — 화면은 이 판정으로 값을 보일지 감출지 정한다 */
export const hasSample = (d) => Boolean(d) && d.n >= MIN_SAMPLE;

/** 국가의 전반 논조 — 표본이 충분한 이슈만 모아 가중 평균.
    결정표 4-1에서 국가 선택 시 톤을 패널 배경으로 옮기기로 했으므로, 그 배경색의 근거가 된다.
    개별 이슈를 볼 때는 절대 이 값을 쓰지 않는다 — 평균은 분열을 지우기 때문이다. */
export function countryToneOf(countryId) {
  let num = 0;
  let den = 0;
  ISSUES.forEach((i) => {
    const d = i.tone[countryId];
    if (!hasSample(d)) return;
    num += d.s * d.n;
    den += d.n;
  });
  return { s: den ? num / den : 0, n: den };
}

/* ═══════════ 검증 ═══════════
   "논조는 있는데 어느 테마에도 안 걸리는 이슈" 같은 조용한 어긋남을 잡는다. */
export function validateModel() {
  const err = [];
  const warn = [];
  const cids = new Set(COUNTRIES.map((c) => c.id));

  ISSUES.forEach((i) => {
    if (!T(i.theme)) err.push(`이슈 ${i.id}: 없는 테마 '${i.theme}'`);
    Object.keys(i.tone).forEach((cid) => {
      if (!cids.has(cid)) err.push(`이슈 ${i.id}: COUNTRIES에 없는 국가 '${cid}'`);
    });
    const low = Object.entries(i.tone).filter(([, d]) => d.n < MIN_SAMPLE).map(([cid]) => C_NAME(cid));
    if (low.length) warn.push(`이슈 ${i.id}(${i.title}): ${low.join(', ')} 표본 부족 — 값 대신 '표본 부족'으로 표시됩니다`);
  });

  THEMES.forEach((t) => {
    if (!FIELD(t.field)) err.push(`테마 ${t.id}: 없는 분야 '${t.field}'`);
    if (!t.issueCount) err.push(`테마 ${t.id}(${t.name}): 소속 이슈가 없습니다`);
  });

  FIELDS.forEach((f) => {
    if (!THEMES.some((t) => t.field === f.id)) warn.push(`분야 ${f.name}: 소속 테마가 없습니다`);
  });

  ARTICLES.forEach((a) => {
    if (!T(a.theme)) err.push(`기사 ${a.id}: 없는 테마 '${a.theme}'`);
    if (!cids.has(a.country)) err.push(`기사 ${a.id}: 없는 국가 '${a.country}'`);
  });

  THEMES.forEach((t) => {
    if (!ARTICLES.some((a) => a.theme === t.id)) {
      warn.push(`테마 ${t.id}(${t.name}): 대표 기사가 없어 대체 문구가 나갑니다`);
    }
  });

  return { err, warn };
}

/** 분야의 논조 — 그 분야에 속한 이슈들을 표본 가중 평균. 테마 단위와 같은 규칙이다. */
export function fieldToneOf(countryId, fieldId) {
  let num = 0;
  let den = 0;
  ISSUES.forEach((i) => {
    if (T(i.theme)?.field !== fieldId) return;
    const d = i.tone[countryId];
    if (!hasSample(d)) return;
    num += d.s * d.n;
    den += d.n;
  });
  return { s: den ? num / den : 0, n: den };
}

/* ═══════════ 조회 도우미 ═══════════ */
export const themesOfField = (fieldId) => (fieldId ? THEMES.filter((t) => t.field === fieldId) : THEMES);
export const issuesOfField = (fieldId) => ISSUES.filter((i) => T(i.theme)?.field === fieldId);
export const issuesOfTheme = (themeId) => ISSUES.filter((i) => i.theme === themeId);
export const articlesOfTheme = (themeId) => ARTICLES.filter((a) => a.theme === themeId);
export const articlesOfCountry = (countryId) => ARTICLES.filter((a) => a.country === countryId);

/** 이슈를 관심도 순으로 — 표본이 많고 증가율이 높은 순 */
export const hotIssues = (limit = 5, countryId = null) =>
  ISSUES.filter((i) => !countryId || i.tone[countryId])
    .slice()
    .sort((a, b) => b.delta - a.delta)
    .slice(0, limit);

/** 국가가 많이 다룬 테마 순 */
export const themesOfCountry = (countryId, limit = 5) =>
  THEMES.map((t) => ({ t, n: themeSampleOf(countryId, t.id) }))
    .filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n)
    .slice(0, limit)
    .map((x) => x.t);

/** 지구본 채색용 — 이슈 하나의 국가별 톤 */
export const toneOverlayOf = (issueId) => {
  const i = I(issueId);
  if (!i) return null;
  return { id: i.id, name: i.title, sub: T_NAME(i.theme), t: i.tone };
};
