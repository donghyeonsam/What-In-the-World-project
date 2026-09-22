import test from 'node:test';
import assert from 'node:assert/strict';
import { notificationApi } from '../src/personalization/notificationApi.js';

test('notification reads retain server pagination, unread counts and settings with session cookies', async () => {
  const original = globalThis.fetch;
  const calls = [];
  const page = { notifications: [{ notificationId: 7, isRead: false }], page: 2, size: 10, hasNext: true };
  const responses = [page, page, { unreadCount: 6 }, { enabled: false }];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, ...options });
    return new Response(JSON.stringify({ status: 200, data: responses.shift() }));
  };
  try {
    assert.deepEqual(await notificationApi.list(), page);
    assert.deepEqual(await notificationApi.list(2, 10), page);
    assert.deepEqual(await notificationApi.unreadCount(), { unreadCount: 6 });
    assert.deepEqual(await notificationApi.settings(), { enabled: false });
    assert.deepEqual(calls.map(({ url }) => url), [
      '/api/v1/notifications?page=1&size=20', '/api/v1/notifications?page=2&size=10',
      '/api/v1/notifications/unread-count', '/api/v1/notifications/settings',
    ]);
    assert.ok(calls.every(({ method, credentials }) => method === 'GET' && credentials === 'include'));
  } finally { globalThis.fetch = original; }
});

test('notification mutations use documented methods and bodies and accept envelopes without data', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, ...options });
    return new Response(JSON.stringify({ status: 200, message: '성공' }));
  };
  try {
    await notificationApi.read('7/8');
    await notificationApi.readAll();
    await notificationApi.remove('9/10');
    await notificationApi.updateSettings(false);
    await notificationApi.updateThemeSettings('11/12', true);
    assert.deepEqual(calls.map(({ url, method, body }) => ({ url, method, body })), [
      { url: '/api/v1/notifications/7%2F8/read', method: 'PATCH', body: undefined },
      { url: '/api/v1/notifications/read-all', method: 'PATCH', body: undefined },
      { url: '/api/v1/notifications/9%2F10', method: 'DELETE', body: undefined },
      { url: '/api/v1/notifications/settings', method: 'PATCH', body: '{"enabled":false}' },
      { url: '/api/v1/notifications/themes/11%2F12/settings', method: 'PATCH', body: '{"enabled":true}' },
    ]);
    assert.ok(calls.every(({ credentials }) => credentials === 'include'));
  } finally { globalThis.fetch = original; }
});

test('notification calls preserve 401 errors for account expiry handling', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ status: 401, message: '로그인이 필요합니다.' }), { status: 401 });
  try {
    const calls = [
      () => notificationApi.list(), () => notificationApi.unreadCount(), () => notificationApi.settings(),
      () => notificationApi.read(1), () => notificationApi.readAll(), () => notificationApi.remove(1),
      () => notificationApi.updateSettings(true), () => notificationApi.updateThemeSettings(1, false),
    ];
    for (const call of calls) await assert.rejects(call(), { status: 401, message: '로그인이 필요합니다.' });
  } finally { globalThis.fetch = original; }
});

test('all notification reads forward cancellation and reject failed reads without placeholder data', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (_, { signal }) => { signal.throwIfAborted(); };
  try {
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(notificationApi.list(1, 20, controller.signal), { name: 'AbortError' });
    await assert.rejects(notificationApi.unreadCount(controller.signal), { name: 'AbortError' });
    await assert.rejects(notificationApi.settings(controller.signal), { name: 'AbortError' });
    globalThis.fetch = async () => new Response(JSON.stringify({ status: 500, message: '알림 조회 실패' }), { status: 500 });
    await assert.rejects(notificationApi.list(), { status: 500 });
  } finally { globalThis.fetch = original; }
});
