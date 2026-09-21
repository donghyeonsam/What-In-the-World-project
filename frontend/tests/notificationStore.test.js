import test from 'node:test';
import assert from 'node:assert/strict';
import { createNotificationStore } from '../src/personalization/notificationStore.js';

const settle = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const unauthorized = () => Object.assign(new Error('로그인이 만료되었습니다.'), { status: 401 });
const item = (id) => ({ id, title: `알림 ${id}`, readAt: null });

test('malformed count/settings keep unknown values and report errors', async (t) => {
  const f = fixture(t);
  f.api.unreadCount = async () => null;
  f.api.settings = async () => ({ enabled: 'true' });
  f.store.start();
  await settle();
  assert.equal(f.store.getSnapshot().unreadCount, null);
  assert.equal(f.store.getSnapshot().enabled, null);
  assert.ok(f.store.getSnapshot().error);
  assert.ok(f.store.getSnapshot().settingsError);
});

test('re-registering interests can discard remembered theme settings', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  await f.store.updateThemeSettings(1, false);
  assert.equal(f.store.getSnapshot().themeSettings[1], false);
  f.store.forgetTheme(1);
  assert.equal(f.store.getSnapshot().themeSettings[1], undefined);
});

function fixture(t, initialItems = [item(2), item(1)]) {
  const calls = [];
  const streams = [];
  const data = { items: initialItems, enabled: true, expired: 0 };
  const api = {
    list: async (page, size, signal) => {
      calls.push({ method: 'list', page, size, signal });
      return { notifications: data.items.slice((page - 1) * size, page * size), page, size, hasNext: data.items.length > page * size };
    },
    unreadCount: async (signal) => {
      calls.push({ method: 'unreadCount', signal });
      return { unreadCount: data.items.filter((row) => !row.readAt).length };
    },
    settings: async (signal) => {
      calls.push({ method: 'settings', signal });
      return { enabled: data.enabled };
    },
    read: async (id) => {
      calls.push({ method: 'read', id });
      data.items = data.items.map((row) => row.id === id ? { ...row, readAt: '2026-09-21T10:00:00' } : row);
    },
    readAll: async () => {
      calls.push({ method: 'readAll' });
      data.items = data.items.map((row) => ({ ...row, readAt: '2026-09-21T10:00:00' }));
    },
    remove: async (id) => {
      calls.push({ method: 'remove', id });
      data.items = data.items.filter((row) => row.id !== id);
    },
    updateSettings: async (enabled) => { calls.push({ method: 'updateSettings', enabled }); data.enabled = enabled; },
    updateThemeSettings: async (id, enabled) => { calls.push({ method: 'updateThemeSettings', id, enabled }); },
  };
  const store = createNotificationStore({
    api,
    connect(callbacks) {
      const stream = { ...callbacks, closed: 0 };
      streams.push(stream);
      return () => { stream.closed++; };
    },
    onExpired() { data.expired++; },
  });
  t.after(() => store.stop());
  return { api, store, calls, streams, data };
}

test('store starts once and loads server list, badge count and global settings', async (t) => {
  const f = fixture(t);
  assert.equal(f.calls.length, 0);
  let changes = 0;
  const unsubscribe = f.store.subscribe(() => changes++);
  f.store.start();
  f.store.start();
  f.streams[0].onState('connected');
  await settle();
  assert.deepEqual(f.store.getSnapshot().items, f.data.items);
  assert.equal(f.store.getSnapshot().unreadCount, 2);
  assert.equal(f.store.getSnapshot().enabled, true);
  assert.equal(f.store.getSnapshot().loading, false);
  assert.equal(f.store.getSnapshot().streamState, 'connected');
  assert.equal(f.streams.length, 1);
  assert.deepEqual(f.calls.map(({ method }) => method), ['list', 'unreadCount', 'settings']);
  assert.equal(f.calls[0].page, 1);
  assert.equal(f.calls[0].size, 20);
  assert.ok(changes > 0);
  unsubscribe();
  const previous = changes;
  await f.store.refresh();
  assert.equal(changes, previous);
});

test('read, delete, read-all and setting mutations reconcile badge and visible records from REST', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  assert.equal(await f.store.read(2), true);
  assert.ok(f.store.getSnapshot().items[0].readAt);
  assert.equal(f.store.getSnapshot().unreadCount, 1);
  assert.equal(await f.store.remove(2), true);
  assert.deepEqual(f.store.getSnapshot().items.map(({ id }) => id), [1]);
  assert.equal(f.store.getSnapshot().unreadCount, 1);
  assert.equal(await f.store.readAll(), true);
  assert.equal(f.store.getSnapshot().unreadCount, 0);
  assert.equal(await f.store.updateSettings(false), true);
  assert.equal(f.store.getSnapshot().enabled, false);
  assert.equal(await f.store.updateThemeSettings(42, false), true);
  assert.deepEqual(f.store.getSnapshot().themeSettings, { 42: false });
  assert.equal(f.store.getSnapshot().busy, '');
  assert.equal(f.calls.filter(({ method }) => method === 'list').length, 6);
});

test('pending mutations exclude concurrent writes and refresh after completion', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  const action = deferred();
  f.api.read = () => action.promise;
  const pending = f.store.read(2);
  assert.equal(f.store.getSnapshot().busy, 'read:2');
  assert.equal(await f.store.remove(1), false);
  await f.store.refresh();
  assert.equal(f.calls.filter(({ method }) => method === 'list').length, 1);
  f.data.items = [{ ...item(2), readAt: '2026-09-21T10:00:00' }, item(1)];
  action.resolve();
  assert.equal(await pending, true);
  assert.equal(f.store.getSnapshot().unreadCount, 1);
  assert.equal(f.store.getSnapshot().busy, '');
});

test('failed mutations retain server records, show the error and release busy state', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  f.api.remove = async () => { throw new Error('삭제 실패'); };
  assert.equal(await f.store.remove(2), false);
  assert.deepEqual(f.store.getSnapshot().items.map(({ id }) => id), [2, 1]);
  assert.equal(f.store.getSnapshot().error, '삭제 실패');
  assert.equal(f.store.getSnapshot().busy, '');
  assert.equal(f.store.getSnapshot().unreadCount, 2);
});

test('more and SSE invalidation reload all visible pages as offsets shift', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const f = fixture(t, Array.from({ length: 22 }, (_, index) => item(22 - index)));
  f.store.start();
  await settle();
  assert.equal(f.store.getSnapshot().hasNext, true);
  await f.store.more();
  assert.equal(f.store.getSnapshot().page, 2);
  assert.equal(f.store.getSnapshot().items.length, 22);
  assert.equal(f.store.getSnapshot().hasNext, false);
  f.calls.length = 0;
  f.data.items.unshift(item(23));
  f.streams[0].onRefresh();
  f.streams[0].onRefresh();
  f.streams[0].onRefresh();
  t.mock.timers.tick(149);
  assert.equal(f.calls.length, 0);
  t.mock.timers.tick(1);
  await settle();
  assert.deepEqual(f.calls.filter(({ method }) => method === 'list').map(({ page }) => page), [1, 2]);
  assert.equal(f.store.getSnapshot().items.length, 23);
  assert.equal(f.store.getSnapshot().items[0].id, 23);
  assert.equal(f.store.getSnapshot().unreadCount, 23);
});

test('overlapping pagination results deduplicate notifications by ID', async (t) => {
  const f = fixture(t);
  f.api.list = async (page) => ({ notifications: page === 1 ? [item(3), item(2)] : [item(2), item(1)], hasNext: page === 1 });
  f.store.start();
  await settle();
  await f.store.more();
  assert.deepEqual(f.store.getSnapshot().items.map(({ id }) => id), [3, 2, 1]);
});

test('partial REST failures preserve loaded records and distinguish settings errors', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  f.api.list = async () => { throw new Error('목록 서버 오류'); };
  f.api.settings = async () => { throw new Error('설정 서버 오류'); };
  f.api.unreadCount = async () => ({ unreadCount: 7 });
  await f.store.refresh();
  const snapshot = f.store.getSnapshot();
  assert.deepEqual(snapshot.items.map(({ id }) => id), [2, 1]);
  assert.equal(snapshot.unreadCount, 7);
  assert.equal(snapshot.enabled, true);
  assert.equal(snapshot.error, '목록 서버 오류');
  assert.equal(snapshot.settingsError, '설정 서버 오류');
  assert.equal(snapshot.loading, false);
});

test('stream errors recheck REST authentication and one 401 expires and clears the store', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const f = fixture(t);
  f.store.start();
  await settle();
  f.api.settings = async () => { throw unauthorized(); };
  f.streams[0].onError(new Error('EventSource cannot expose its HTTP status'));
  t.mock.timers.tick(150);
  await settle();
  assert.equal(f.data.expired, 1);
  assert.equal(f.streams[0].closed, 1);
  assert.deepEqual(f.store.getSnapshot().items, []);
  assert.equal(f.store.getSnapshot().unreadCount, null);
  assert.equal(f.store.getSnapshot().enabled, null);
  const count = f.calls.length;
  f.streams[0].onRefresh();
  f.streams[0].onError();
  t.mock.timers.tick(150);
  await f.store.refresh();
  assert.equal(f.calls.length, count);
  assert.equal(f.data.expired, 1);
});

test('mutation 401 clears account data and does not perform a reconciliation request', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  f.api.readAll = async () => { throw unauthorized(); };
  assert.equal(await f.store.readAll(), false);
  assert.equal(f.data.expired, 1);
  assert.deepEqual(f.store.getSnapshot().items, []);
  assert.deepEqual(f.store.getSnapshot().themeSettings, {});
  assert.equal(f.store.getSnapshot().busy, '');
  assert.equal(f.calls.filter(({ method }) => method === 'list').length, 1);
});

test('a 401 from any visible page expires the session even if another page fails first', async (t) => {
  const f = fixture(t, Array.from({ length: 22 }, (_, index) => item(22 - index)));
  f.store.start();
  await settle();
  await f.store.more();
  f.api.list = async (page) => {
    if (page === 1) throw Object.assign(new Error('일시적인 서버 오류'), { status: 500 });
    throw unauthorized();
  };
  await f.store.refresh();
  assert.equal(f.data.expired, 1);
  assert.deepEqual(f.store.getSnapshot().items, []);
  assert.equal(f.streams[0].closed, 1);
});

test('stopping aborts requests and discards late data and queued SSE work', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const f = fixture(t);
  const first = deferred();
  let requestSignal;
  f.api.list = (_, __, signal) => { requestSignal = signal; return first.promise; };
  f.store.start();
  f.streams[0].onRefresh();
  f.store.stop();
  const snapshot = f.store.getSnapshot();
  assert.equal(requestSignal.aborted, true);
  first.resolve({ notifications: [item(99)], hasNext: false });
  f.streams[0].onState('connected');
  t.mock.timers.tick(150);
  await settle();
  assert.equal(f.store.getSnapshot(), snapshot);
  assert.equal(f.streams[0].closed, 1);
  assert.equal(f.data.expired, 0);
});

test('restart generation rejects old 401 results while retaining the new generation data', async (t) => {
  const f = fixture(t);
  const first = deferred();
  const list = f.api.list;
  f.api.list = () => first.promise;
  f.store.start();
  f.store.stop();
  f.api.list = list;
  f.data.items = [item(88)];
  f.store.start();
  await settle();
  first.reject(unauthorized());
  await settle();
  assert.equal(f.data.expired, 0);
  assert.deepEqual(f.store.getSnapshot().items.map(({ id }) => id), [88]);
  assert.equal(f.streams.length, 2);
  assert.equal(f.streams[1].closed, 0);
});

test('switching accounts closes the old stream and isolates late mutation failures', async (t) => {
  const previousAccount = fixture(t, [item(11)]);
  previousAccount.store.start();
  await settle();
  const oldAction = deferred();
  previousAccount.api.remove = () => oldAction.promise;
  const pending = previousAccount.store.remove(11);
  previousAccount.store.stop();
  const nextAccount = fixture(t, [item(99)]);
  nextAccount.store.start();
  await settle();
  oldAction.reject(unauthorized());
  assert.equal(await pending, false);
  assert.equal(previousAccount.data.expired, 0);
  assert.equal(previousAccount.streams[0].closed, 1);
  assert.equal(nextAccount.data.expired, 0);
  assert.deepEqual(nextAccount.store.getSnapshot().items.map(({ id }) => id), [99]);
  assert.equal(nextAccount.streams[0].closed, 0);
});

test('a newer refresh wins even if the aborted older request resolves later', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  const slow = deferred();
  const list = f.api.list;
  let staleSignal;
  f.api.list = (_, __, signal) => { staleSignal = signal; return slow.promise; };
  const oldRefresh = f.store.refresh();
  f.api.list = list;
  f.data.items = [item(77)];
  await f.store.refresh();
  assert.equal(staleSignal.aborted, true);
  slow.resolve({ notifications: [item(66)], hasNext: false });
  await oldRefresh;
  assert.deepEqual(f.store.getSnapshot().items.map(({ id }) => id), [77]);
});

test('restart after stopping a pending mutation resets busy state and ignores old completion', async (t) => {
  const f = fixture(t);
  f.store.start();
  await settle();
  const old = deferred();
  f.api.read = () => old.promise;
  const pending = f.store.read(2);
  f.store.stop();
  f.store.start();
  await settle();
  assert.equal(f.store.getSnapshot().busy, '');
  old.reject(unauthorized());
  assert.equal(await pending, false);
  assert.equal(f.data.expired, 0);
  assert.equal(f.streams[1].closed, 0);
});
