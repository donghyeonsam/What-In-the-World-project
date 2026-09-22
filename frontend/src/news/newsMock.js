// 실제 보도가 아닌 UI 확인용 예시. DTO는 실제 API 어댑터와 동일하다.
export const mockFilters = {
  countries: [ ['KR', '대한민국'], ['US', '미국'], ['JP', '일본'], ['GB', '영국'], ['DE', '독일'] ]
    .map(([countryCode, countryName]) => ({ countryCode, countryName })),
  fields: [
    { fieldId: 1, fieldName: '경제', themes: [{ themeId: 11, themeName: '금융' }, { themeId: 12, themeName: '부동산' }] },
    { fieldId: 2, fieldName: '과학·기술', themes: [{ themeId: 21, themeName: '인공지능' }, { themeId: 22, themeName: '우주' }] },
    { fieldId: 3, fieldName: '사회', themes: [{ themeId: 31, themeName: '교육' }, { themeId: 32, themeName: '환경' }] },
    { fieldId: 4, fieldName: '스포츠', themes: [{ themeId: 41, themeName: '야구' }, { themeId: 42, themeName: '축구' }] },
  ],
};
const headlines = {
  11: ['금리 변화 속 금융 시장의 다음 흐름은', '지역 기업을 위한 투자 지원 논의 확대'],
  12: ['주거 환경 개선을 위한 도시의 새로운 실험', '달라지는 주택 시장, 공급과 수요를 살피다'],
  21: ['일상으로 들어온 인공지능, 활용과 책임을 묻다', '기업의 AI 도입 확산, 산업 현장의 변화'],
  22: ['새로운 우주 탐사 계획이 그리는 미래', '위성 기술로 바라본 지구 환경의 변화'],
  31: ['교실에서 시작되는 디지털 교육의 변화', '지역과 학교가 함께 만드는 배움의 기회'],
  32: ['도시의 탄소 배출을 줄이는 작은 변화들', '재생에너지 전환을 위한 지역 협력 확대'],
  41: ['시즌 막바지 순위 경쟁, 주목할 관전 포인트', '신인 선수 육성과 구단의 장기 전략'],
  42: ['새 시즌을 준비하는 팀들의 전술 변화', '지역 축구의 저변을 넓히는 유소년 활동'],
};
const themes = mockFilters.fields.flatMap((field) => field.themes.map((theme) => ({ ...theme, fieldId: field.fieldId, fieldName: field.fieldName })));
const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' });
// 모든 국가·테마 조합을 포함하고 최근 180일에 분포한다.
export const mockArticles = Array.from({ length: 360 }, (_, index) => {
  const country = mockFilters.countries[index % 5];
  const theme = themes[Math.floor(index / 5) % themes.length];
  const day = new Date(`${today}T12:00:00+09:00`);
  day.setUTCDate(day.getUTCDate() - Math.floor(index / 2));
  day.setUTCMinutes(index % 60);
  return {
    articleId: `demo-${String(index + 1).padStart(4, '0')}`,
    articleTitle: `[예시] ${country.countryName} · ${headlines[theme.themeId][Math.floor(index / 40) % 2]}`,
    summary: `이 내용은 뉴스 화면을 확인하기 위한 가상 기사 요약입니다. 실제 보도를 인용하지 않았습니다.\n\n${country.countryName}의 ${theme.themeName} 관련 변화를 살펴보는 예시로, 주요 배경과 현장의 반응, 향후 논의할 과제를 소개합니다. 실제 API가 연결되면 서버에서 제공하는 기사 요약이 이곳에 표시됩니다.`,
    articlePublisher: '샘플 뉴스룸', publishedAt: day.toISOString(),
    ...country, ...theme, url: 'https://example.com/',
  };
});
export const mockNewsSource = {
  async filters({ signal } = {}) { signal?.throwIfAborted(); return mockFilters; },
  async list(query, { signal } = {}) {
    signal?.throwIfAborted();
    const rows = mockArticles.filter((a) => {
      const date = new Date(new Date(a.publishedAt).getTime() + 9 * 3600000).toISOString().slice(0, 10);
      return (!query.countryCode || a.countryCode === query.countryCode)
        && (!query.fieldId || String(a.fieldId) === query.fieldId)
        && (!query.themeId || String(a.themeId) === query.themeId)
        && (!query.from || date >= query.from) && (!query.to || date <= query.to);
    }).sort((a, b) => b.publishedAt.localeCompare(a.publishedAt) || b.articleId.localeCompare(a.articleId));
    const { page, size } = query;
    return { items: rows.slice((page - 1) * size, page * size), page, size, totalElements: rows.length, totalPages: Math.ceil(rows.length / size) };
  },
  async detail(id, { signal } = {}) {
    signal?.throwIfAborted();
    const article = mockArticles.find((a) => a.articleId === id);
    if (!article) throw new Error('기사를 찾을 수 없습니다.');
    return article;
  },
};
