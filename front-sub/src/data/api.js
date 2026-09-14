import { demoDashboard, demoCountry, getDemoIssue, articles, filterArticles, countries } from './demo.js';

const BASE = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
export async function request(path, { signal, method = 'GET', body, params = {} } = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''));
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timeout = setTimeout(abort, 12000);
  try {
    const response = await fetch(`${BASE}${path}${query.size ? `?${query}` : ''}`, { method, signal: controller.signal, credentials: 'include', headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
    const json = await response.json().catch(() => null);
    if (!response.ok || !json || json.status >= 400) throw new Error(json?.message || `API 응답 오류 (${response.status})`);
    // Auth success responses intentionally omit data.
    return json.data ?? null;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (controller.signal.aborted) throw new Error('서버 응답이 지연되고 있습니다. 다시 시도해 주세요.');
    throw error;
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}
export function normalizeArticle(a, scope = {}) {
  return { ...scope, id: a.articleId, title: a.articleTitle || a.originalTitle || '제목 미제공', publisher: a.articlePublisher || '매체 미제공', publishedAt: a.publishedAt, tone: a.articleTone?.toLowerCase() || 'unknown', url: safeUrl(a.url), summary: a.summary || '', demo: false };
}
export function safeUrl(value) { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : null; } catch { return null; } }
function normalizeTones(rows = []) { return rows.map(row => ({ ...(countries.find(c => c.code === row.country.countryCode) || {}), code: row.country.countryCode, name: row.country.countryName, lat: row.country.latitude, lon: row.country.longitude, average: row.toneAvg, count: row.articleCount, sd: row.toneSd, min: row.toneMin, max: row.toneMax })); }
export const services = {
  async dashboard(mode, signal) {
    if (mode === 'demo') return demoDashboard();
    const [data, catalog] = await Promise.all([request('/global/issues', { signal }), request('/themes/by-field', { signal })]);
    return { total: data.totalArticleCount, recent: data.recent24ArticleCount, source: 'live', fields: catalog.map(f => ({ id: f.fieldId, name: f.fieldName, themes: f.themes.map(t => ({ id: t.themeId, name: t.themeName, count: t.articleCount24 })) })), issues: data.globalIssues.map(i => ({ id: i.issueId, title: i.issueName, shortTitle: i.issueName, count: i.articleCount, firstSeenAt: i.firstSeenAt, themeName: i.themeName, fieldName: i.fieldName, demo: false })) };
  },
  async issue(id, mode, signal) {
    if (mode === 'demo') return getDemoIssue(id);
    const [info, overview] = await Promise.all([request(`/global/issues/${id}`, { signal }), request(`/issues/${id}/overview`, { signal, params: { articleLimit: 10 } })]);
    return { id: Number(id), title: info.issueInfo.issueName, shortTitle: info.issueInfo.issueName, count: info.issueInfo.articleCount, countryCount: info.issueInfo.countryCount, themeName: overview.issuePreview.themeTitle, summary: '', countryTones: normalizeTones(overview.countryTones), articles: overview.representArticles.map(a => normalizeArticle(a, { issueId: Number(id) })), source: 'live', demo: false };
  },
  async country(code, mode, signal) {
    if (mode === 'demo') return demoCountry(code);
    const [data, popular] = await Promise.all([request(`/countries/${code}`, { signal }), request(`/countries/${code}/themes/popular`, { signal, params: { limit: 10 } })]);
    const mention = rows => rows.map(r => ({ code: r.countryCode, name: r.countryName, ratio: r.mentionRatio }));
    return { code, name: data.countryName, recent: data.todayArticleCount, rank: data.globalRank, themes: popular.popularThemes.map(t => ({ id: t.themeId, name: t.themeName, count: t.articleCount24, field: t.fieldName, trend: t.themeTimeStamp?.timestamp?.map(p => p.articleCount) || [] })), outgoing: mention(data.sourceMentions), incoming: mention(data.targetMentions), articles: data.representArticles.map(a => normalizeArticle(a, { countryCode: code })), source: 'live' };
  },
  async countryArticles(issueId, code, mode, signal) {
    if (mode === 'demo') return articles.filter(a => a.issueId === Number(issueId) && a.countryCode === code);
    const data = await request(`/issues/${issueId}/overview`, { signal, params: { articleLimit: 10, countryCode: code } });
    return data.representArticles.map(a => normalizeArticle(a, { issueId: Number(issueId), countryCode: code }));
  },
  async explore(filters, mode, signal) {
    // There is no full article search endpoint. Its prototype is explicitly demo-only.
    if (mode === 'demo') return { articles: filterArticles(articles, filters), source: 'demo', limited: false };
    if (!filters.theme) return { articles: [], source: 'live', chooseTheme: true };
    const data = await request(`/themes/${filters.theme}/overview`, { signal, params: { issueLimit: 10, articleLimit: 10, countryCode: filters.country } });
    const list = data.representArticles.map(a => normalizeArticle(a, { themeId: Number(filters.theme), countryCode: filters.country || null }));
    return { articles: list.filter(a => (!filters.tone || filters.tone === 'all' || a.tone === filters.tone) && (!filters.query || `${a.title} ${a.publisher}`.includes(filters.query))), issues: data.primaryIssues, description: data.themeDescription, source: 'live', limited: true };
  },
};
