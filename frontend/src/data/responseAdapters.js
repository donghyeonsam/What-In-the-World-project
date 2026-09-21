export const fmt = (value) => value == null ? '—' : Number(value).toLocaleString('ko-KR');
export const flagOf = (code = '') => /^[a-z]{2}$/i.test(code)
  ? String.fromCodePoint(...code.toUpperCase().split('').map((letter) => letter.charCodeAt(0) + 127397)) : '🌐';
export const scoreOf = (score) => score == null ? null : Math.max(-1, Math.min(1, Number(score) / 50 - 1));
export function dateLabel(value) {
  if (!value) return '발행 시각 없음';
  const date = new Date(/[zZ]$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}+09:00`);
  return Number.isNaN(date.getTime()) ? '발행 시각 없음' : new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}
export function safeUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
export function articleCard(article) {
  const tone = (article.articleTone || 'NEUTRAL').toLowerCase();
  return {
    id: article.articleId, title: article.articleTitle || '제목 없음', tone,
    toneLabel: { positive: '긍정', neutral: '중립', negative: '부정' }[tone] || '분석 없음',
    source: article.articlePublisher || '매체 미상', time: dateLabel(article.publishedAt),
    summary: article.summary || '', url: safeUrl(article.url),
  };
}
export function themeCard(theme) {
  const counts = theme.themeTimeStamp?.timestamp?.map((point) => point.articleCount) || [];
  const max = Math.max(1, ...counts);
  return {
    id: theme.themeId, name: theme.themeName, field: theme.fieldName,
    count: fmt(theme.articleCount24), bars: counts.map((count) => count / max * 100),
    timestamps: theme.themeTimeStamp?.timestamp,
  };
}
export function mentionRows(mentions = []) {
  return mentions.map((row) => {
    const percent = Math.max(0, Math.min(100, row.mentionRatio * 100));
    return [flagOf(row.countryCode), row.countryName, `${percent.toFixed(1)}%`, percent, '', row.countryCode];
  });
}
export function globeTones(rows = [], countryCode) {
  return Object.fromEntries(rows.filter((row) => !countryCode || row.country.countryCode.toUpperCase() === countryCode.toUpperCase())
    .map((row) => [row.country.countryCode.toLowerCase(), { s: scoreOf(row.toneAvg), n: row.articleCount ?? null }]));
}
