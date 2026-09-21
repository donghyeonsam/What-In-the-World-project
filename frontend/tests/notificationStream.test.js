import test from 'node:test';
import assert from 'node:assert/strict';
import { API_BASE } from '../src/data/api.js';
import { connectNotificationStream } from '../src/personalization/notificationStream.js';

function fixture() {
  const streams = [];
  const timers = new Map();
  let now = 0;
  let nextId = 0;
  class FakeEventSource {
    constructor(url, options) {
      this.url = url;
      this.options = options;
      this.listeners = new Map();
      this.closed = false;
      streams.push(this);
    }
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    removeEventListener(type, callback) { if (this.listeners.get(type) === callback) this.listeners.delete(type); }
    emit(type) { this.listeners.get(type)?.({ type }); }
    close() { this.closed = true; }
  }
  const options = {
    EventSourceImpl: FakeEventSource,
    setTimeoutFn: (callback, delay) => {
      const id = ++nextId;
      timers.set(id, { callback, due: now + delay });
      return id;
    },
    clearTimeoutFn: (id) => timers.delete(id),
  };
  function tick(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...timers.entries()].sort((a, b) => a[1].due - b[1].due)[0];
      if (!next || next[1].due > end) break;
      now = next[1].due;
      timers.delete(next[0]);
      next[1].callback();
    }
    now = end;
  }
  return { streams, timers, options, tick };
}

test('stream uses the shared API base and cookies and only invalidation events refresh REST data', () => {
  const f = fixture();
  const states = [];
  const refreshes = [];
  const close = connectNotificationStream({ ...f.options, onState: (state) => states.push(state), onRefresh: (type) => refreshes.push(type) });
  const source = f.streams[0];
  assert.equal(source.url, `${API_BASE}/notifications/subscribe`);
  assert.deepEqual(source.options, { withCredentials: true });
  source.emit('open');
  source.emit('connected');
  source.emit('heartbeat');
  source.emit('notifications-changed');
  assert.deepEqual(refreshes, ['connected', 'notifications-changed']);
  assert.deepEqual(states, ['connecting', 'connected']);
  close();
  assert.equal(source.closed, true);
  assert.equal(source.listeners.size, 0);
  assert.equal(f.timers.size, 0);
  assert.equal(states.at(-1), 'closed');
});

test('heartbeats extend liveness and a silent connection closes before retrying', () => {
  const f = fixture();
  const errors = [];
  const close = connectNotificationStream({ ...f.options, onError: (error) => errors.push(error) });
  const first = f.streams[0];
  first.emit('connected');
  f.tick(45_000);
  first.emit('heartbeat');
  f.tick(45_000);
  assert.equal(first.closed, false);
  f.tick(15_000);
  assert.equal(first.closed, true);
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /응답이 지연/);
  assert.equal(f.streams.length, 1);
  f.tick(2_999);
  assert.equal(f.streams.length, 1);
  f.tick(1);
  assert.equal(f.streams.length, 2);
  close();
  assert.equal(f.timers.size, 0);
});

test('CLOSED and repeated handshake errors reconnect with capped backoff and ignore stale events', () => {
  const f = fixture();
  const close = connectNotificationStream(f.options);
  const expectedDelays = [3_000, 6_000, 12_000, 24_000, 30_000, 30_000];
  for (const delay of expectedDelays) {
    const previous = f.streams.at(-1);
    const staleError = previous.listeners.get('error');
    previous.emit('connected');
    previous.readyState = 2;
    previous.emit('error');
    staleError({ type: 'error' });
    assert.equal(previous.closed, true);
    assert.equal(previous.listeners.size, 0);
    assert.equal(f.timers.size, 1);
    const count = f.streams.length;
    f.tick(delay - 1);
    assert.equal(f.streams.length, count);
    f.tick(1);
    assert.equal(f.streams.length, count + 1);
  }
  f.streams.at(-1).emit('heartbeat');
  f.streams.at(-1).emit('error');
  const count = f.streams.length;
  f.tick(3_000);
  assert.equal(f.streams.length, count + 1);
  close();
});

test('cleanup during backoff cancels retry and prevents events from reopening the stream', () => {
  const f = fixture();
  let refreshes = 0;
  const close = connectNotificationStream({ ...f.options, onRefresh: () => refreshes++ });
  const first = f.streams[0];
  const staleRefresh = first.listeners.get('notifications-changed');
  first.emit('error');
  close();
  close();
  staleRefresh();
  f.tick(120_000);
  assert.equal(refreshes, 0);
  assert.equal(f.streams.length, 1);
  assert.equal(f.timers.size, 0);
});

test('unsupported EventSource fails once and constructor failures use delayed retry', () => {
  const f = fixture();
  const errors = [];
  const states = [];
  const closeUnsupported = connectNotificationStream({
    ...f.options, EventSourceImpl: null, onState: (state) => states.push(state), onError: (error) => errors.push(error),
  });
  assert.deepEqual(states, ['closed']);
  assert.equal(errors.length, 1);
  assert.equal(f.timers.size, 0);
  closeUnsupported();
  let attempts = 0;
  const close = connectNotificationStream({ ...f.options, EventSourceImpl: class { constructor() { attempts++; throw new Error('network'); } } });
  assert.equal(attempts, 1);
  f.tick(2_999);
  assert.equal(attempts, 1);
  f.tick(1);
  assert.equal(attempts, 2);
  close();
  assert.equal(f.timers.size, 0);
});

test('rejected async callbacks do not escape EventSource dispatch or trigger reconnect loops', async () => {
  const f = fixture();
  let errors = 0;
  const close = connectNotificationStream({
    ...f.options,
    onState: async () => { throw new Error('state consumer failed'); },
    onRefresh: async () => { throw new Error('REST failed'); },
    onError: async () => { errors++; throw new Error('error consumer failed'); },
  });
  f.streams[0].emit('connected');
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(errors, 1);
  assert.equal(f.streams.length, 1);
  assert.equal(f.streams[0].closed, false);
  close();
  await Promise.resolve();
});
