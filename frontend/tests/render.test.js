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
    const { default: Feed, ArticleFilterBar } = await vite.ssrLoadModule('/src/components/panel/ArticleFeed.jsx');
    const filters = render(ArticleFilterBar, { tone: 'positive' });
    assert.match(filters, /aria-label="기사 논조 필터"/);
    assert.match(filters, /aria-pressed="true">긍정/);
    const { CountryIdentity } = await vite.ssrLoadModule('/src/components/panel/PanelChrome.jsx');
    assert.doesNotMatch(render(CountryIdentity, { flag: '🇰🇷', name: '대한민국' }), /<p/);
    const article = articleCard({ articleId: '1', articleTitle: '<script>제목</script>', articleTone: 'POSITIVE', articlePublisher: '매체', publishedAt: '2026-09-08T12:00:00' });
    const feed = render(Feed, { articles: [article] });
    assert.match(feed, /&lt;script&gt;/); assert.match(feed, /긍정/);
    assert.match(feed, /원문 링크가 제공되지 않았습니다/); assert.doesNotMatch(feed, /<button/);
    assert.match(render(Feed, { articles: [] }), /조건에 맞는 기사가 없습니다/);
    const { default: Tones } = await vite.ssrLoadModule('/src/components/panel/ApiToneScatter.jsx');
    const tone = render(Tones, { rows: [{ country: { countryCode: 'KR', countryName: '한국' }, toneAvg: 75, toneMin: 40, toneMax: 90, toneSd: 12.5, articleCount: 40 }] });
    assert.match(tone, /한국/); assert.match(tone, /\+0.50/); assert.match(tone, /40건/);
    assert.match(tone, /σ 0.25 · 보통/);
    assert.doesNotMatch(tone, /미국|30일 평시/);
    assert.match(render(Tones, { rows: [] }), /논조 데이터가 없습니다/);
    const oneArticle = render(Tones, { rows: [{ country: { countryCode: 'US', countryName: '미국' }, toneAvg: 20, toneMin: 20, toneMax: 20, toneSd: 0, articleCount: 1 }] });
    assert.match(oneArticle, /편차 산출 불가/);
    assert.match(oneArticle, /최소 -0.60 \/ 평균 -0.60 \/ 최대 -0.60/);
    assert.match(oneArticle, /toneRange/);
    assert.match(oneArticle, /toneFill/);
    assert.match(tone, /<details[^>]*><summary>논조 해석 기준<\/summary>/);
    assert.doesNotMatch(tone, /<details[^>]*\bopen\b/);
    const smallSample = render(Tones, { rows: [{ country: { countryCode: 'JP', countryName: '일본' }, toneAvg: 40, toneMin: 30, toneMax: 50, toneSd: 5, articleCount: 2 }] });
    assert.match(smallSample, /σ 0.10 · 참고용/);
    const { default: Attention } = await vite.ssrLoadModule('/src/components/panel/AttentionPanel.jsx');
    const attention = render(Attention, { country: '한국', direction: 'incoming', rows: [['🇬🇧', '영국', '60.0%', 60, '']] });
    assert.match(attention, /영국에서 가장 많이 언급/); assert.match(attention, /60.0%/); assert.doesNotMatch(attention, /미국|31.2/);
    assert.match(render(Attention, { country: '한국', direction: 'outgoing', rows: [] }), /언급 데이터가 없습니다/);
    const { default: App } = await vite.ssrLoadModule('/src/App.jsx');
    assert.match(render(App, {}), /데이터를 불러오고 있습니다/);
  } finally { await vite.close(); }
});
