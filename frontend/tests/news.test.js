import test from 'node:test';
import assert from 'node:assert/strict';
import { readNewsQuery, newsSearch, queryError } from '../src/news/newsQuery.js';
import { mockNewsSource, mockFilters, mockArticles } from '../src/news/newsMock.js';
import { httpNewsSource, isMockNews, newsSource } from '../src/news/newsSource.js';

test('news query survives share/reload and rejects invalid dates, pages and taxonomy', () => {
  const query = { countryCode: 'KR', fieldId: '2', themeId: '21', from: '2026-01-01', to: '2026-09-16', page: 3 };
  assert.deepEqual(readNewsQuery(newsSearch(query)), query);
  assert.equal(readNewsQuery('?page=-2&from=2026-02-30').page, 1);
  assert.equal(readNewsQuery('?from=2026-02-30').from, '');
  assert.equal(queryError(query, mockFilters), '');
  assert.ok(queryError({ ...query, from: '2027-01-01' }, mockFilters));
  assert.ok(queryError({ ...query, themeId: '11' }, mockFilters));
  assert.ok(queryError({ ...query, countryCode: 'ZZ' }, mockFilters));
});

test('mock pagination filters the whole archive before slicing; detail shares the same identity', async () => {
  const query = { ...readNewsQuery(''), size: 12 };
  const first = await mockNewsSource.list(query);
  const second = await mockNewsSource.list({ ...query, page: 2 });
  assert.equal(first.totalElements, 360);
  assert.equal(first.totalPages, 30);
  assert.equal(first.items.length, 12);
  assert.ok(second.items.every((item) => !first.items.some((a) => a.articleId === item.articleId)));
  const filtered = await mockNewsSource.list({ ...query, countryCode: 'KR', fieldId: '2', themeId: '21' });
  assert.ok(filtered.totalElements > 0);
  assert.ok(filtered.items.every((a) => a.countryCode === 'KR' && a.themeId === 21 && a.fieldId === 2));
  const detail = await mockNewsSource.detail(first.items[0].articleId);
  assert.equal(detail.articleTitle, first.items[0].articleTitle);
  assert.ok(detail.summary && detail.url);
  const day = new Date(new Date(mockArticles[0].publishedAt).getTime() + 9 * 3600000).toISOString().slice(0, 10);
  const daily = await mockNewsSource.list({ ...query, from: day, to: day });
  assert.equal(daily.totalElements, 2);
  assert.equal((await mockNewsSource.list({ ...query, page: 100 })).items.length, 0);
  assert.equal((await mockNewsSource.list({ ...query, from: '1900-01-01', to: '1900-01-02' })).totalElements, 0);
  await assert.rejects(mockNewsSource.detail('missing'));
  const controller = new AbortController(); controller.abort();
  await assert.rejects(mockNewsSource.list(query, { signal: controller.signal }), { name: 'AbortError' });
});

test('HTTP source uses documented endpoints, query and envelope without mock fallback', async () => {
  assert.equal(isMockNews, false);
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(new URL(url, 'http://localhost'));
    return { ok: true, status: 200, json: async () => ({ status: 200, data: { marker: 'server' } }) };
  };
  try {
    await httpNewsSource.filters();
    await newsSource.filters();
    const result = await httpNewsSource.list({ countryCode: 'KR', fieldId: '2', themeId: '21', from: '2026-01-01', to: '2026-09-16', page: 2, size: 12 });
    await httpNewsSource.detail('article/id');
    assert.equal(calls[0].pathname, '/api/v1/articles/filters');
    assert.equal(calls[1].pathname, '/api/v1/articles/filters');
    assert.equal(calls[2].searchParams.get('page'), '2');
    assert.equal(calls[2].searchParams.get('countryCode'), 'KR');
    assert.equal(calls[3].pathname, '/api/v1/articles/article%2Fid');
    assert.equal(result.marker, 'server');
    globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({ message: 'server error' }) });
    await assert.rejects(httpNewsSource.list({ page: 1, size: 12 }), /server error/);
  } finally { globalThis.fetch = originalFetch; }
});
