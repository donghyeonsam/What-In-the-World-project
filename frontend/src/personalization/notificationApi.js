import { request } from '../data/api.js';

const patch = (path, body) => request(path, { method: 'PATCH', body, allowEmpty: true });

export const notificationApi = {
  list: (page = 1, size = 20, signal) => request('/notifications', { signal, params: { page, size } }),
  unreadCount: (signal) => request('/notifications/unread-count', { signal }),
  read: (id) => patch(`/notifications/${encodeURIComponent(id)}/read`),
  readAll: () => patch('/notifications/read-all'),
  remove: (id) => request(`/notifications/${encodeURIComponent(id)}`, { method: 'DELETE', allowEmpty: true }),
  settings: (signal) => request('/notifications/settings', { signal }),
  updateSettings: (enabled) => patch('/notifications/settings', { enabled }),
  updateThemeSettings: (themeId, enabled) => patch(`/notifications/themes/${encodeURIComponent(themeId)}/settings`, { enabled }),
};
