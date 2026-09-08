import test from 'node:test';
import assert from 'node:assert/strict';
import { api, request, ApiError } from '../src/data/api.js';
import { articleCard, themeCard, mentionRows, globeTones, scoreOf, safeUrl } from '../src/data/responseAdapters.js';

test('all seven existing endpoints use the documented query limits and response envelope', async () => {
  const original = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async (url) => { urls.push(url); return new Response(JSON.stringify({ status: 200, data: [] })); };
  try {
    await api.dashboard(); await api.fields(); await api.country('kr'); await api.popular('kr');
    await api.theme(7); await api.issue(11); await api.overview(11);
    assert.deepEqual(urls, ['/api/v1/global/issues', '/api/v1/themes/by-field', '/api/v1/countries/KR',
      '/api/v1/countries/KR/themes/popular?limit=10', '/api/v1/themes/7/overview?issueLimit=10&articleLimit=10',
      '/api/v1/global/issues/11', '/api/v1/issues/11/overview?articleLimit=10']);
  } finally { globalThis.fetch = original; }
});
test('API errors, invalid envelopes, and cancellation do not become sample data', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ status: 404, message: '테마가 없습니다.' }), { status: 404 });
    await assert.rejects(request('/themes/999/overview'), { message: '테마가 없습니다.', status: 404 });
    globalThis.fetch = async () => new Response('<html>proxy error</html>');
    await assert.rejects(request('/global/issues'), ApiError);
    const controller = new AbortController(); controller.abort();
    globalThis.fetch = async (_, { signal }) => { signal.throwIfAborted(); };
    await assert.rejects(request('/global/issues', { signal: controller.signal }), { name: 'AbortError' });
  } finally { globalThis.fetch = original; }
});
test('country scope never includes foreign tone and absent sample sizes remain unknown', () => {
  const rows = [{ country: { countryCode: 'KR' }, toneAvg: 75, articleCount: 40 }, { country: { countryCode: 'US' }, toneAvg: 10, articleCount: 20 }];
  assert.deepEqual(globeTones(rows, 'KR'), { kr: { s: .5, n: 40 } });
  assert.deepEqual(globeTones(rows, 'GB'), {});
  assert.equal(Object.keys(globeTones(rows)).length, 2);
  assert.equal(scoreOf(0), -1); assert.equal(scoreOf(50), 0); assert.equal(scoreOf(100), 1);
  assert.equal(scoreOf(null), null);
});
test('articles retain actual tone and date, and never manufacture original links', () => {
  const card = articleCard({ articleId: 'a', articleTitle: '기사', articleTone: 'NEGATIVE', articlePublisher: '매체', publishedAt: '2026-09-08T12:30:00' });
  assert.equal(card.tone, 'negative'); assert.equal(card.toneLabel, '부정');
  assert.equal(card.url, null); assert.equal(card.summary, ''); assert.match(card.time, /12:30/);
  assert.equal(safeUrl('javascript:alert(1)'), null);
  assert.equal(safeUrl('https://example.com/news'), 'https://example.com/news');
});
test('mention ratios use 0–1 API scale and hourly counts come from actual timestamps', () => {
  assert.deepEqual(mentionRows([{ countryCode: 'US', countryName: '미국', mentionRatio: .312 }])[0].slice(1), ['미국', '31.2%', 31.2, '']);
  const card = themeCard({ themeId: 1, themeName: '경제', articleCount24: 5, themeTimeStamp: { timestamp: [{ articleCount: 0 }, { articleCount: 5 }] } });
  assert.deepEqual(card.bars, [0, 100]); assert.equal(card.rise, undefined);
});
