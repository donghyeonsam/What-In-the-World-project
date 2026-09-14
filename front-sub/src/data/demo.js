// All stories and statistics in this file are fictional fixtures, not reported news.
export const countries = [
  { code: 'KR', name: '대한민국', english: 'South Korea', flag: '🇰🇷', lat: 36.5, lon: 127.8 },
  { code: 'US', name: '미국', english: 'United States', flag: '🇺🇸', lat: 38, lon: -97 },
  { code: 'JP', name: '일본', english: 'Japan', flag: '🇯🇵', lat: 36.2, lon: 138.3 },
  { code: 'DE', name: '독일', english: 'Germany', flag: '🇩🇪', lat: 51.2, lon: 10.4 },
  { code: 'GB', name: '영국', english: 'United Kingdom', flag: '🇬🇧', lat: 54, lon: -2 },
];
export const fields = [
  { id: 1, name: '경제', themes: [{ id: 11, name: '반도체 & 공급망' }, { id: 12, name: '글로벌 무역' }] },
  { id: 2, name: '과학·기술', themes: [{ id: 21, name: '인공지능' }, { id: 22, name: '우주 탐사' }] },
  { id: 3, name: '환경', themes: [{ id: 31, name: '에너지 전환' }, { id: 32, name: '기후 행동' }] },
  { id: 4, name: '사회·문화', themes: [{ id: 41, name: '도시와 삶' }, { id: 42, name: '문화 교류' }] },
];
const now = Date.now();
export const issues = [
  { id: 101, fieldId: 1, themeId: 11, title: '반도체 공급망의 재편,\n세계는 어디를 향하나', shortTitle: '반도체 공급망 재편', summary: '생산 거점 다변화와 기술 협력이라는 하나의 변화를 각국은 어떻게 해석할까요? 산업 경쟁력부터 공급 안정성까지, 국가별로 다른 보도 초점을 비교해 보세요.', count: 1284, change: 24, tags: ['공급망', '산업 정책', '기술 협력'], tones: [68, 39, 57, 48, 62], samples: [342, 416, 218, 186, 122] },
  { id: 102, fieldId: 2, themeId: 21, title: '일상에 들어온 AI,\n혁신과 규칙 사이', shortTitle: 'AI 혁신과 새로운 규칙', summary: 'AI 활용이 넓어지며 기업의 책임과 사회적 합의에 대한 논의도 이어집니다. 각국 매체가 무엇을 먼저 이야기하는지 살펴보세요.', count: 963, change: 18, tags: ['AI', '규제', '디지털 사회'], tones: [72, 63, 66, 34, 46], samples: [218, 293, 141, 180, 131] },
  { id: 103, fieldId: 3, themeId: 31, title: '에너지 전환의 속도,\n나라별로 다른 해법', shortTitle: '에너지 전환의 다음 단계', summary: '재생에너지 투자와 전력망 확충이 주요 과제로 떠올랐습니다. 에너지 안보와 기후 대응의 접점을 비교합니다.', count: 746, change: 12, tags: ['재생에너지', '전력망', '기후'], tones: [45, 42, 58, 74, 69], samples: [105, 173, 84, 220, 164] },
  { id: 104, fieldId: 1, themeId: 12, title: '새로운 무역의 질서,\n협력의 길을 묻다', shortTitle: '무역 질서와 경제 협력', summary: '변화하는 교역 환경 속에서 각국의 수출 전략과 경제 협력 논의가 만납니다.', count: 592, change: -7, tags: ['무역', '경제 협력'], tones: [42, 32, 54, 48, 57], samples: [128, 166, 92, 114, 92] },
  { id: 105, fieldId: 4, themeId: 41, title: '도시의 내일,\n더 나은 일상을 위한 실험', shortTitle: '지속 가능한 도시의 실험', summary: '교통과 주거, 공공 공간을 바꾸려는 도시의 시도들이 이어집니다. 시민의 일상을 중심으로 새로운 해법을 읽어봅니다.', count: 318, change: 9, tags: ['도시', '모빌리티'], tones: [67, 55, 73, 62, 58], samples: [88, 76, 19, 71, 64] },
].map((issue, index) => ({ ...issue, firstSeenAt: new Date(now - (index + 1) * 3600000 * 7).toISOString(), demo: true }));
const angles = [
  ['국내 산업의 기회와 과제', '투자 확대와 공급 안정성에 주목', '기술 협력을 통한 새로운 성장 가능성'],
  ['정책 변화가 산업 경쟁에 미칠 영향', '기업 전략과 국제 협력의 균형', '장기 투자에 대한 시장의 시선'],
  ['기업의 대응과 기술 전환', '지역 산업이 찾는 새로운 기회', '연구 개발 협력의 다음 단계'],
  ['산업 정책과 지속 가능성', '유럽의 협력 전략에 주목', '전환 비용과 사회적 합의'],
  ['국제 협력의 가능성과 쟁점', '새로운 시장과 정책의 역할', '다양한 목소리로 살펴본 변화'],
];
export const articles = issues.flatMap((issue, ii) => countries.flatMap((country, ci) => angles[ci].map((angle, ai) => ({
  id: `demo-${issue.id}-${country.code}-${ai}`, issueId: issue.id, themeId: issue.themeId, fieldId: issue.fieldId,
  countryCode: country.code, title: `${issue.shortTitle}: ${angle}`, originalTitle: '',
  publisher: `${country.name} 샘플 미디어 ${ai + 1}`, publishedAt: new Date(now - (ii * 4 + ci + ai + 1) * 3600000).toISOString(),
  tone: toneName(issue.tones[ci] + (ai - 1) * 12), score: issue.tones[ci] + (ai - 1) * 12,
  summary: `${country.name}의 보도 관점을 살펴보기 위한 가상 기사입니다. ${issue.summary} 이 예시에서는 ${angle.toLowerCase()}을 중심으로 배경과 쟁점을 정리합니다. 실제 보도나 매체의 입장을 인용한 내용이 아닙니다.`,
  url: null, demo: true,
}))));
export function toneName(score) { return score <= 33 ? 'negative' : score <= 66 ? 'neutral' : 'positive'; }
export const toneLabels = { positive: '긍정', neutral: '중립', negative: '부정', unknown: '분석 없음' };
export function themeById(id) { return fields.flatMap(f => f.themes).find(t => t.id === Number(id)); }
export function countryByCode(code) { return countries.find(c => c.code === code); }
export function getDemoIssue(id) {
  const issue = issues.find(i => i.id === Number(id));
  if (!issue) throw new Error('데모 데이터에 없는 이슈입니다. 이슈 목록에서 다시 선택해 주세요.');
  return { ...issue, countryTones: countries.map((c, index) => ({ ...c, average: issue.tones[index], count: issue.samples[index], sd: 8 + index * 2, min: Math.max(0, issue.tones[index] - 18), max: Math.min(100, issue.tones[index] + 22) })), articles: articles.filter(a => a.issueId === issue.id), source: 'demo' };
}
export function filterArticles(list, filters = {}) {
  return list.filter(a => (!filters.country || a.countryCode === filters.country) && (!filters.theme || a.themeId === Number(filters.theme)) && (!filters.field || a.fieldId === Number(filters.field)) && (!filters.issue || a.issueId === Number(filters.issue)) && (!filters.tone || filters.tone === 'all' || a.tone === filters.tone) && (!filters.query || `${a.title} ${a.publisher}`.toLowerCase().includes(filters.query.toLowerCase())) && (!filters.hours || new Date(a.publishedAt).getTime() >= now - Number(filters.hours) * 3600000));
}
export function demoDashboard() { return { total: 148296, recent: 8246, issues, fields, source: 'demo' }; }
export function demoCountry(code) {
  const country = countryByCode(code);
  if (!country) throw new Error('지원하지 않는 국가입니다.');
  const ci = countries.indexOf(country);
  return { ...country, recent: [1842, 2916, 1230, 1348, 910][ci], rank: [2, 1, 4, 3, 5][ci], source: 'demo',
    themes: fields.slice(0, 3).map((f, i) => ({ id: f.themes[0].id, name: f.themes[0].name, field: f.name, count: [642, 481, 315][i] - ci * 21, trend: Array.from({ length: 24 }, (_, h) => 5 + ((h * 7 + ci * 3 + i * 11) % 24) + Math.floor(h / 4)) })),
    outgoing: countries.filter(c => c.code !== code).map((c, i) => ({ ...c, ratio: [0.42, 0.28, 0.18, 0.12][i] })),
    incoming: countries.filter(c => c.code !== code).reverse().map((c, i) => ({ ...c, ratio: [0.36, 0.29, 0.22, 0.13][i] })),
    articles: articles.filter(a => a.countryCode === code).slice(0, 8), issues,
  };
}
