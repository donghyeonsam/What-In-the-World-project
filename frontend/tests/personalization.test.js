import test from 'node:test';
import assert from 'node:assert/strict';
import { parseInterests, loadPersonalNews, accountStorageKey } from '../src/personalization/model.js';
import { accountApi } from '../src/personalization/accountApi.js';
import { createSsafyAuthorizeUrl, readSsafyCallback } from '../src/personalization/ssafyOAuth.js';

const interests = { countries: [], themes: [{ id: 1, name: '경제' }], issues: [{ id: 2, name: '금리' }] };
test('interests reject malformed values and isolate storage by account', () => {
  assert.deepEqual(parseInterests('broken'), { countries: [], themes: [], issues: [] });
  assert.deepEqual(parseInterests('{"countries":[{"id":"KR","name":"한국"},{"id":"bad","name":"오류"}],"themes":[null,{"id":1,"name":"경제"},{"id":1,"name":"중복"}]}'), { countries: [{ id: 'KR', name: '한국' }], themes: [{ id: 1, name: '경제' }], issues: [] });
  assert.notEqual(accountStorageKey(1), accountStorageKey(2));
});
test('subscription news deduplicates keywords/issues and sorts dates including offsets', async () => {
  const source = { list: async () => ({ items: [{ articleId: 'a', publishedAt: '2026-09-01T10:00:00+09:00' }], totalElements: 15 }) };
  const api = { overview: async () => ({ representArticles: [{ articleId: 'a' }, { articleId: 'b', publishedAt: '2026-09-01T02:00:00Z' }] }) };
  const result = await loadPersonalNews(interests, source, api);
  assert.deepEqual(result.articles.map((a) => a.articleId), ['b', 'a']);
  assert.deepEqual(result.articles[1].matches, ['경제', '금리']);
  assert.equal(result.hasMore, true);
});
test('country selection narrows every keyword and issue request', async () => {
  const calls = [];
  const api = { overview: async (id, country) => { calls.push({ id, country }); return { representArticles: [] }; } };
  const source = { list: async (query) => { calls.push(query); return { items: [] }; } };
  await loadPersonalNews({ ...interests, countries: [{ id: 'KR', name: '한국' }] }, source, api);
  assert.deepEqual(calls, [{ countryCode: 'KR', themeId: 1, page: 1, size: 12 }, { id: 2, country: 'KR' }]);
});
test('country-only subscriptions do not invent keyword filters; no interests sends no requests', async () => {
  const calls = [];
  const source = { list: async (query) => { calls.push(query); return { items: [] }; } };
  await loadPersonalNews({ countries: [{ id: 'US', name: '미국' }], themes: [], issues: [] }, source, {});
  assert.equal(calls[0].countryCode, 'US'); assert.equal(calls[0].themeId, undefined);
  await loadPersonalNews({ countries: [], themes: [], issues: [] }, source, {});
  assert.equal(calls.length, 1);
});
test('partial failures retain successful news; cancellation stops subsequent batches', async () => {
  const result = await loadPersonalNews(interests, { list: async () => { throw new Error('offline'); } }, { overview: async () => ({ representArticles: [{ articleId: 'a' }] }) });
  assert.deepEqual(result.failed, ['경제']); assert.equal(result.articles.length, 1);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(loadPersonalNews(interests, {}, {}, controller.signal), { name: 'AbortError' });
});
test('account API sends session cookies, correct bodies and accepts success without data', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({ url, ...options }); return new Response(JSON.stringify({ status: 200, message: '성공' })); };
  try {
    await accountApi.login('test@example.com', 'test-password');
    await accountApi.ssafyLogin('authorization-code');
    await accountApi.signup('test@example.com', 'test-password');
    await accountApi.sendCode('test@example.com');
    await accountApi.verifyCode('test@example.com', 'AB12345');
    await accountApi.changePassword('old-password', 'new-password');
    await accountApi.logout();
    assert.ok(calls.every((call) => call.credentials === 'include'));
    assert.equal(calls[0].method, 'POST');
    assert.deepEqual(JSON.parse(calls[0].body), { email: 'test@example.com', password: 'test-password' });
    assert.equal(calls[1].url, '/api/v1/auth/ssafy');
    assert.deepEqual(JSON.parse(calls[1].body), { code: 'authorization-code' });
    assert.equal(calls[5].method, 'PATCH'); assert.equal(calls[5].url, '/api/v1/users/password');
    assert.deepEqual(JSON.parse(calls[5].body), { currentPassword: 'old-password', newPassword: 'new-password' });
    globalThis.fetch = async () => new Response(JSON.stringify({ status: 401, message: '로그인 필요' }), { status: 401 });
    await assert.rejects(accountApi.me(), { status: 401 });
  } finally { globalThis.fetch = original; }
});

test('SSAFY callback validates state once and restores the pre-login URL', () => {
  const values = new Map([
    ['witw_ssafy_oauth_state', 'safe-state'],
    ['witw_ssafy_oauth_return', '/?view=news&page=2'],
  ]);
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
  };
  assert.deepEqual(readSsafyCallback('?code=one-time-code&state=safe-state', storage), {
    code: 'one-time-code', returnUrl: '/?view=news&page=2',
  });
  assert.equal(values.size, 0);
  assert.throws(() => readSsafyCallback('?code=replayed&state=safe-state', storage), /확인할 수 없습니다/);
});

test('SSAFY authorization uses the registered callback URI', () => {
  const storage = { setItem: () => {} };
  const url = new URL(createSsafyAuthorizeUrl({
    pathname: '/', search: '', hash: '',
  }, storage, () => 'safe-state'));
  assert.equal(url.searchParams.get('redirect_uri'), 'https://dev.witw.kro.kr/auth/ssafy/callback');
});
