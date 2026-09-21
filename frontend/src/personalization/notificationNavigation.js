import { newsSearch } from '../news/newsQuery.js';

function positiveId(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return '';
  if (!/^[1-9]\d*$/.test(String(value))) return '';
  return Number.isSafeInteger(Number(value)) ? String(value) : '';
}

export function notificationNewsUrl(notification) {
  return newsSearch({
    fieldId: positiveId(notification?.fieldId),
    themeId: positiveId(notification?.themeId),
    page: 1,
  });
}

export function navigateToNotificationNews(notification) {
  const url = new URL(window.location.href);
  url.search = notificationNewsUrl(notification);
  url.hash = '';
  if (url.href !== window.location.href) window.history.pushState(null, '', url.href);
  // Notify the query-based router even when this notification is already open.
  window.dispatchEvent(new Event('popstate'));
  return url.href;
}
