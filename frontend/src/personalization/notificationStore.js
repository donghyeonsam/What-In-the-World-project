// A per-login store: late responses from an old account must never update a new one.
export function createNotificationStore({ api, connect, onExpired }) {
  const listeners = new Set();
  let state = {
    items: [], page: 1, hasNext: false, unreadCount: null, enabled: null,
    loading: true, busy: '', error: '', settingsError: '', streamState: 'connecting',
    themeSettings: {}, arrival: null,
  };
  let active = false;
  let generation = 0;
  let requestVersion = 0;
  let controller;
  let closeStream;
  let timer;
  let writing = false;
  let arrivalSequence = 0;
  const update = (patch) => { state = { ...state, ...patch }; listeners.forEach((fn) => fn()); };
  const current = (version) => active && generation === version;
  const stop = () => {
    active = false; generation++; requestVersion++;
    controller?.abort(); closeStream?.(); clearTimeout(timer);
    closeStream = null;
  };
  const fail = (error) => {
    if (error?.status !== 401) return false;
    stop();
    update({ items: [], unreadCount: null, enabled: null, themeSettings: {}, busy: '', loading: false });
    onExpired?.();
    return true;
  };
  async function refresh(page = state.page, announce = false) {
    if (!active || writing) return;
    const previousItems = state.items;
    const previousUnreadCount = state.unreadCount;
    clearTimeout(timer);
    controller?.abort();
    const requestController = new AbortController();
    controller = requestController;
    const run = ++requestVersion;
    const version = generation;
    update({ loading: true, error: '', settingsError: '' });
    // Reload all visible pages after mutations/new events: offset pagination shifts.
    const results = await Promise.allSettled([
      Promise.allSettled(Array.from({ length: page }, (_, index) => api.list(index + 1, 20, requestController.signal)))
        .then((pages) => {
          const failure = pages.find((part) => part.status === 'rejected' && part.reason?.status === 401)
            || pages.find((part) => part.status === 'rejected');
          if (failure) throw failure.reason;
          const values = pages.map((part) => part.value);
          if (values.some((part) => !Array.isArray(part?.notifications) || typeof part.hasNext !== 'boolean')) {
            throw new Error('알림 목록 응답을 확인하지 못했습니다.');
          }
          return values;
        }),
      api.unreadCount(requestController.signal), api.settings(requestController.signal),
    ]);
    if (!current(version) || run !== requestVersion) return;
    const unauthorized = results.find((result) => result.status === 'rejected' && result.reason?.status === 401);
    if (unauthorized) { fail(unauthorized.reason); return; }
    const patch = { loading: false };
    const [list, count, settings] = results;
    if (list.status === 'fulfilled') {
      const unique = new Map();
      for (const part of list.value) for (const item of part.notifications) unique.set(String(item.id), item);
      patch.items = [...unique.values()];
      patch.page = page;
      patch.hasNext = list.value.at(-1).hasNext;
    } else patch.error = list.reason.message || '알림을 불러오지 못했습니다.';
    if (count.status === 'fulfilled' && Number.isSafeInteger(count.value?.unreadCount) && count.value.unreadCount >= 0) patch.unreadCount = count.value.unreadCount;
    else patch.error = patch.error || count.reason?.message || '미읽음 개수를 확인하지 못했습니다.';
    if (announce && Array.isArray(patch.items) && Number.isSafeInteger(previousUnreadCount) && patch.unreadCount > previousUnreadCount) {
      const knownIds = new Set(previousItems.map((item) => String(item.id)));
      const arrived = patch.items.find((item) => !item.readAt && !knownIds.has(String(item.id)));
      if (arrived) patch.arrival = { ...arrived, token: ++arrivalSequence };
    }
    if (settings.status === 'fulfilled' && typeof settings.value?.enabled === 'boolean') patch.enabled = settings.value.enabled;
    else patch.settingsError = settings.reason?.message || '알림 설정을 불러오지 못했습니다.';
    update(patch);
  }
  function scheduleRefresh(announce = false) {
    if (!active) return;
    clearTimeout(timer);
    timer = setTimeout(() => { void refresh(state.page, announce); }, 150);
  }
  async function mutate(key, action, patch) {
    if (!active || writing) return false;
    const version = generation;
    writing = true;
    controller?.abort(); requestVersion++;
    update({ busy: key, error: '', loading: false });
    let success = false;
    let actionError = '';
    try {
      await action();
      if (!current(version)) return false;
      if (patch) update(patch(state));
      success = true;
    } catch (error) {
      if (!current(version) || fail(error)) return false;
      actionError = error.message || '처리하지 못했습니다. 다시 시도해 주세요.';
    } finally {
      if (current(version)) {
        writing = false;
        // Reconcile counts and lists instead of incrementing/decrementing guesses.
        await refresh();
        if (current(version)) update({ busy: '', ...(actionError ? { error: actionError } : {}) });
      }
    }
    return current(version) && success;
  }
  return {
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    getSnapshot: () => state,
    start() {
      if (active) return stop;
      active = true; generation++; writing = false;
      update({ busy: '', streamState: 'connecting' });
      const version = generation;
      void refresh();
      closeStream = connect({
        onRefresh: (eventType) => { if (current(version)) scheduleRefresh(eventType === 'notifications-changed'); },
        onState: (streamState) => { if (current(version)) update({ streamState }); },
        // REST exposes a 401; EventSource errors don't expose HTTP response codes.
        onError: () => { if (current(version)) scheduleRefresh(); },
      });
      return stop;
    },
    stop,
    forgetTheme(id) {
      const themeSettings = { ...state.themeSettings };
      delete themeSettings[id];
      update({ themeSettings });
    },
    refresh: () => refresh(),
    more: () => !state.loading && !state.busy && state.hasNext ? refresh(state.page + 1) : Promise.resolve(),
    read: (id) => mutate(`read:${id}`, () => api.read(id)),
    readAll: () => mutate('read-all', () => api.readAll()),
    remove: (id) => mutate(`delete:${id}`, () => api.remove(id)),
    updateSettings: (enabled) => mutate('settings', () => api.updateSettings(enabled), () => ({ enabled })),
    updateThemeSettings: (id, enabled) => mutate(`theme:${id}`, () => api.updateThemeSettings(id, enabled),
      (old) => ({ themeSettings: { ...old.themeSettings, [id]: enabled } })),
  };
}
