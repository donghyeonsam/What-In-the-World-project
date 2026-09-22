import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('theme picker renders and searches the full 68-theme catalog', async () => {
  const vite = await createServer({ configFile: false, server: { middlewareMode: true }, appType: 'custom', esbuild: { jsx: 'automatic' }, optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const { ThemePicker } = await vite.ssrLoadModule('/src/personalization/Personalization.jsx');
    const fields = Array.from({ length: 4 }, (_, fieldIndex) => ({
      fieldId: fieldIndex + 1,
      fieldName: `분야 ${fieldIndex + 1}`,
      themes: Array.from({ length: 17 }, (_, themeIndex) => ({
        themeId: fieldIndex * 17 + themeIndex + 1,
        themeName: `테마 ${fieldIndex * 17 + themeIndex + 1}`,
      })),
    }));
    const props = { fields, selected: [{ id: 1, name: '테마 1' }], pending: [], query: '', setQuery() {}, toggle() {}, disabled: false };
    const html = renderToStaticMarkup(React.createElement(ThemePicker, props));
    assert.match(html, /1<small> \/ 68개 선택<\/small>/);
    assert.equal((html.match(/aria-pressed=/g) || []).length, 68);
    assert.match(html, /전체 테마 68개/);

    const searched = renderToStaticMarkup(React.createElement(ThemePicker, { ...props, query: '테마 68' }));
    assert.equal((searched.match(/aria-pressed=/g) || []).length, 1);
    assert.match(searched, /테마 68/);
    assert.doesNotMatch(searched, />테마 67</);
  } finally {
    await vite.close();
  }
});
