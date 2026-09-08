import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { articleCard } from '../src/data/responseAdapters.js';

test('screens render real DTO fields, empty states, and missing-data notices', async () => {
  const vite = await createServer({ configFile: false, server: { middlewareMode: true }, appType: 'custom', esbuild: { jsx: 'automatic' }, optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
    const { default: Feed } = await vite.ssrLoadModule('/src/components/panel/ArticleFeed.jsx');
    const article = articleCard({ articleId: '1', articleTitle: '<script>제목</script>', articleTone: 'POSITIVE', articlePublisher: '매체', publishedAt: '2026-09-08T12:00:00' });
    const feed = render(Feed, { articles: [article] });
    assert.match(feed, /&lt;script&gt;/); assert.match(feed, /긍정/);
    assert.match(feed, /원문 링크가 제공되지 않았습니다/); assert.doesNotMatch(feed, /<button/);
    assert.match(render(Feed, { articles: [] }), /조건에 맞는 기사가 없습니다/);
    const { default: Tones } = await vite.ssrLoadModule('/src/components/panel/ApiToneScatter.jsx');
    const tone = render(Tones, { rows: [{ country: { countryCode: 'KR', countryName: '한국' }, toneAvg: 75, toneMin: 40, toneMax: 90 }] });
    assert.match(tone, /한국/); assert.match(tone, /\+0.50/); assert.match(tone, /표본 수 미제공/);
    assert.doesNotMatch(tone, /미국|30일 평시/);
    assert.match(render(Tones, { rows: [] }), /논조 데이터가 없습니다/);
    const { default: Attention } = await vite.ssrLoadModule('/src/components/panel/AttentionPanel.jsx');
    const attention = render(Attention, { country: '한국', direction: 'incoming', rows: [['🇬🇧', '영국', '60.0%', 60, '']] });
    assert.match(attention, /영국에서 가장 많이 언급/); assert.match(attention, /60.0%/); assert.doesNotMatch(attention, /미국|31.2/);
    assert.match(render(Attention, { country: '한국', direction: 'outgoing', rows: [] }), /언급 데이터가 없습니다/);
    const { default: App } = await vite.ssrLoadModule('/src/App.jsx');
    assert.match(render(App, {}), /데이터를 불러오고 있습니다/);
  } finally { await vite.close(); }
});
