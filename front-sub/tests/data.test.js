import test from 'node:test';
import assert from 'node:assert/strict';
import { articles, countries, issues, filterArticles, getDemoIssue, demoCountry } from '../src/data/demo.js';
import { normalizeArticle, request, safeUrl, services } from '../src/data/api.js';
import { parseRoute, routeSearch } from '../src/hooks.js';

test('demo data preserves issue/country relationships and explicitly marks fictional articles', () => {
  assert.equal(new Set(articles.map(a => a.id)).size, articles.length);
  for (const issue of issues) {
    const detail = getDemoIssue(issue.id);
    assert.equal(detail.countryTones.reduce((sum, c) => sum + c.count, 0), issue.count);
    for (const country of countries) assert.equal(detail.articles.filter(a => a.countryCode === country.code).length, 3);
  }
  assert.ok(articles.every(a => a.demo && a.url === null));
  assert.throws(() => getDemoIssue(999), /없는 이슈/);
  assert.throws(() => demoCountry('ZZ'), /지원하지 않는 국가/);
});
test('combined filters apply to the entire fixture set before display limits', () => {
  const found = filterArticles(articles, { country: 'KR', field: '1', theme: '11', issue: '101', tone: 'positive', query: '공급망' });
  assert.ok(found.length > 0);
  assert.ok(found.every(a => a.countryCode === 'KR' && a.themeId === 11 && a.issueId === 101 && a.tone === 'positive'));
  assert.equal(filterArticles(articles, { query: 'not-a-real-title' }).length, 0);
});
test('URL state supports direct links, Unicode article IDs and at most two distinct comparison countries', () => {
  const input = parseRoute('?page=explore&theme=11&country=KR&issue=101&compare=KR,US,KR,JP&article=demo-101-KR-0');
  assert.deepEqual(parseRoute(routeSearch(input)), input);
  assert.deepEqual(input.compare, ['KR', 'US']);
  assert.equal(parseRoute('?page=unknown&issue=invalid&country=bad').page, 'world');
  assert.equal(parseRoute('?issue=invalid').issue, '');
});
test('live article missing fields never receive fabricated title/summary/url', () => {
  const a = normalizeArticle({ articleId: 'live-1', articleTone: 'NEUTRAL' });
  assert.equal(a.title, '제목 미제공'); assert.equal(a.summary, ''); assert.equal(a.url, null); assert.equal(a.demo, false);
  assert.equal(safeUrl('javascript:alert(1)'), null);
  assert.equal(safeUrl('https://example.com/article'), 'https://example.com/article');
});
test('auth success without data is accepted, API failure remains an error', async () => {
  const original = global.fetch;
  try {
    global.fetch = async (_, options) => { assert.equal(options.credentials, 'include'); return new Response(JSON.stringify({ status: 200, message: 'success' })); };
    assert.equal(await request('/auth/login', { method: 'POST', body: { email: 'test@example.com', password: 'test-only' } }), null);
    global.fetch = async () => new Response(JSON.stringify({ status: 503, message: '서버 점검' }), { status: 503 });
    await assert.rejects(services.dashboard('live'), /서버 점검/);
  } finally { global.fetch = original; }
});
test('existing issue overview is requested with publisher country and current limit', async () => {
  const original = global.fetch;
  try {
    global.fetch = async url => { assert.equal(url, '/api/v1/issues/17/overview?articleLimit=10&countryCode=KR'); return new Response(JSON.stringify({ status: 200, data: { representArticles: [{ articleId: '1', articleTitle: '실제 제목' }] } })); };
    const result = await services.countryArticles('17', 'KR', 'live');
    assert.equal(result[0].countryCode, 'KR'); assert.equal(result[0].demo, false);
    const noSearch = await services.explore({}, 'live');
    assert.equal(noSearch.chooseTheme, true); assert.equal(noSearch.articles.length, 0);
  } finally { global.fetch = original; }
});
