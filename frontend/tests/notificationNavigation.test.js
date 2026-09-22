import test from 'node:test';
import assert from 'node:assert/strict';
import { notificationNewsUrl, navigateToNotificationNews } from '../src/personalization/notificationNavigation.js';
import { readNewsQuery, queryError } from '../src/news/newsQuery.js';
import { mockFilters, mockNewsSource } from '../src/news/newsMock.js';

test('notification links select the supplied field and theme on page one', async () => {
  const url = notificationNewsUrl({ fieldId: 2, themeId: 21 });
  assert.equal(url, '?view=news&fieldId=2&themeId=21&page=1');
  const query = readNewsQuery(url);
  assert.deepEqual(query, {
    countryCode: '', fieldId: '2', themeId: '21', from: '', to: '', page: 1,
  });
  assert.equal(queryError(query, mockFilters), '');
  const result = await mockNewsSource.list({ ...query, size: 12 });
  assert.ok(result.items.length > 0);
  assert.ok(result.items.every((article) => article.fieldId === 2 && article.themeId === 21));
});

test('notification links accept integer strings without borrowing unrelated notification fields', () => {
  assert.equal(notificationNewsUrl({
    fieldId: '2', themeId: '21', id: 8, countryCode: 'KR', page: 7,
    from: '2026-09-01', to: '2026-09-02', asOf: '2026-09-01T00:00:00',
    url: 'https://example.com/',
  }), '?view=news&fieldId=2&themeId=21&page=1');
  assert.equal(notificationNewsUrl({ id: 21, fieldName: '경제', themeName: '금리' }), '?view=news&page=1');
  assert.equal(notificationNewsUrl(null), '?view=news&page=1');
});

test('malformed and unsafe identifiers cannot become news filters', () => {
  const invalid = [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1,
    '', '0', '-1', '1.5', '1e2', '01', ' 2 ', '2&countryCode=KR', '9007199254740992', true, {}, [], null];
  for (const id of invalid) {
    assert.equal(notificationNewsUrl({ fieldId: id, themeId: id }), '?view=news&page=1');
  }
  assert.equal(notificationNewsUrl({ fieldId: 'bad', themeId: 21 }), '?view=news&themeId=21&page=1');
});

test('notification navigation clears previous filters and time travel while keeping the app base path', () => {
  const original = globalThis.window;
  const events = [];
  const changes = [];
  let current = new URL('https://example.com/app/?view=news&countryCode=KR&fieldId=1&themeId=11&from=2026-09-01&to=2026-09-02&page=7&asOf=2026-09-01T00%3A00%3A00#old');
  globalThis.window = {
    get location() { return current; },
    history: { pushState(state, title, url) {
      changes.push({ state, title, url });
      current = new URL(url, current);
    } },
    dispatchEvent(event) { events.push({ type: event.type, href: current.href }); },
  };
  try {
    const expected = 'https://example.com/app/?view=news&fieldId=2&themeId=21&page=1';
    assert.equal(navigateToNotificationNews({ fieldId: 2, themeId: 21 }), expected);
    assert.equal(current.href, expected);
    assert.deepEqual(changes, [{ state: null, title: '', url: expected }]);
    assert.deepEqual(events, [{ type: 'popstate', href: expected }]);

    // Reopening the same notification still tells App to synchronize/reload.
    navigateToNotificationNews({ fieldId: 2, themeId: 21 });
    assert.equal(changes.length, 1);
    assert.deepEqual(events, [{ type: 'popstate', href: expected }, { type: 'popstate', href: expected }]);
  } finally {
    if (original === undefined) delete globalThis.window;
    else globalThis.window = original;
  }
});
