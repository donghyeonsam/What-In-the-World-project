import { API_BASE } from '../data/api.js';

// SSE carries invalidation signals; the owner reloads notification data through REST.
export function connectNotificationStream({
  onRefresh, onState, onError,
  EventSourceImpl = globalThis.EventSource,
  setTimeoutFn = globalThis.setTimeout,
  clearTimeoutFn = globalThis.clearTimeout,
  heartbeatTimeoutMs = 60_000,
  retryDelayMs = 3_000,
  maxRetryDelayMs = 30_000,
} = {}) {
  let stopped = false;
  let source = null;
  let detach = null;
  let heartbeatTimer = null;
  let retryTimer = null;
  let retryAttempt = 0;
  let state;

  const emit = (callback, value, reportError = false) => {
    const rejected = (error) => {
      if (reportError && !stopped) emit(onError, error);
    };
    try { Promise.resolve(callback?.(value)).catch(rejected); }
    catch (error) { rejected(error); }
  };
  const setState = (next) => {
    if (state !== next) { state = next; emit(onState, next); }
  };
  const disconnect = () => {
    clearTimeoutFn(heartbeatTimer);
    heartbeatTimer = null;
    detach?.();
    detach = null;
    const previous = source;
    source = null;
    previous?.close();
  };
  const close = () => {
    if (stopped) return;
    stopped = true;
    clearTimeoutFn(retryTimer);
    retryTimer = null;
    disconnect();
    setState('closed');
  };
  const retry = (error) => {
    if (stopped || retryTimer !== null) return;
    disconnect();
    // Close the native stream before retrying, including terminal CLOSED errors.
    const delay = Math.min(maxRetryDelayMs, retryDelayMs * (2 ** Math.min(retryAttempt++, 10)));
    retryTimer = setTimeoutFn(() => { retryTimer = null; connect(); }, delay);
    setState('retrying');
    emit(onError, error);
  };
  const watchHeartbeat = () => {
    clearTimeoutFn(heartbeatTimer);
    heartbeatTimer = setTimeoutFn(() => {
      retry(new Error('실시간 알림 연결의 응답이 지연되고 있습니다.'));
    }, heartbeatTimeoutMs);
  };
  const connect = () => {
    if (stopped) return;
    setState('connecting');
    try {
      const current = new EventSourceImpl(`${API_BASE}/notifications/subscribe`, { withCredentials: true });
      source = current;
      const active = () => !stopped && source === current;
      const connected = () => {
        if (!active()) return;
        watchHeartbeat();
        setState('connected');
      };
      const refresh = (event) => {
        if (!active()) return;
        connected();
        emit(onRefresh, event?.type, true);
      };
      const heartbeat = () => {
        if (!active()) return;
        // A heartbeat proves the connection survived the initial handshake.
        retryAttempt = 0;
        connected();
      };
      const failed = (event) => { if (active()) retry(event); };
      const listeners = { open: connected, connected: refresh, 'notifications-changed': refresh, heartbeat, error: failed };
      Object.entries(listeners).forEach(([type, listener]) => current.addEventListener(type, listener));
      detach = () => Object.entries(listeners).forEach(([type, listener]) => current.removeEventListener(type, listener));
      watchHeartbeat();
    } catch (error) { retry(error); }
  };

  if (typeof EventSourceImpl !== 'function') {
    close();
    emit(onError, new Error('이 브라우저는 실시간 알림 연결을 지원하지 않습니다.'));
  } else connect();
  return close;
}
