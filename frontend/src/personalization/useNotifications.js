import { useEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import { notificationApi } from './notificationApi.js';
import { connectNotificationStream } from './notificationStream.js';
import { createNotificationStore } from './notificationStore.js';

export function useNotifications(userId, onExpired) {
  const expired = useRef(onExpired);
  expired.current = onExpired;
  const store = useMemo(() => createNotificationStore({
    api: notificationApi,
    connect: connectNotificationStream,
    onExpired: () => expired.current(),
  }), [userId]);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  useEffect(() => {
    if (!userId) return;
    const stop = store.start();
    const refresh = () => { if (!document.hidden) void store.refresh(); };
    window.addEventListener('online', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      stop(); window.removeEventListener('online', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [userId, store]);
  return { ...state, store };
}
