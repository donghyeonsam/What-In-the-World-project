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
    const { default: Globe } = await vite.ssrLoadModule('/src/components/globe/GlobeThree.jsx');
    const globe = render(Globe, { countries: [] });
    assert.match(globe, /지구를 불러오는 중…/);
    assert.match(globe, /aria-busy="true"/);
    assert.match(globe, /disabled=""/);
    assert.match(globe, /aria-label="지구 자전 멈춤"/);
    assert.match(globe, /aria-pressed="true"/);
    assert.match(globe, /자전 중/);
    assert.doesNotMatch(render(Globe, { countries: [], spinControl: false }), /지구 자전 멈춤/);
    const previousMatchMedia = globalThis.matchMedia;
    try {
      globalThis.matchMedia = () => ({ matches: true });
      const reducedGlobe = render(Globe, { countries: [] });
      assert.match(reducedGlobe, /aria-label="지구 자전 재개"/);
      assert.match(reducedGlobe, /aria-pressed="false"/);
    } finally {
      if (previousMatchMedia === undefined) delete globalThis.matchMedia;
      else globalThis.matchMedia = previousMatchMedia;
    }
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
    const { default: Perspectives } = await vite.ssrLoadModule('/src/components/panel/IssuePerspectives.jsx');
    const emptyAnalysis = { data: null, loading: false, error: null, retry() {} };
    const renderPerspectives = (props) => render(Perspectives, { countryAnalyses: emptyAnalysis, analysis: emptyAnalysis, ...props });
    const perspectiveData = { issuePreview: { issueTitle: '테스트 이슈', themeTitle: '안보' }, countryTones: [
      { country: { countryCode: 'KR', countryName: '한국' }, articleCount: 40, toneAvg: 75 },
      { country: { countryCode: 'US', countryName: '미국' }, articleCount: 20, toneAvg: null },
    ] };
    const perspectives = renderPerspectives({ data: perspectiveData, issueId: 1, spot: null });
    assert.match(perspectives, /국가별 언론의 보도 관점/);
    assert.match(perspectives, /보도량 순 · 2개국/);
    assert.match(perspectives, /논조 분석 없음/);
    assert.match(perspectives, /등록된 분석 없음/);
    assert.doesNotMatch(perspectives, /이슈 발생국|연결선/);
    const analysisSummary = { analysisId: 7, countryCode: 'KR', title: '공급망 재편 주목', summary: '협력의 필요성을 보도', articleCount: 12, windowEnd: '2026-09-18T10:00:00+09:00' };
    const analysisDetail = { ...analysisSummary, issueId: 1, title: '선택한 국가의 상세 제목', details: ['기업별 대응을 분석', '두 번째 보도 관점', '세 번째 보도 관점'] };
    const detailResource = { ...emptyAnalysis, data: analysisDetail };
    const analyzed = renderPerspectives({ data: perspectiveData,
      countryAnalyses: { ...emptyAnalysis, data: { issueId: 1, countryAnalyses: [analysisSummary] } },
      analysis: detailResource, issueId: 1, spot: 'kr' });
    assert.match(analyzed, /공급망 재편 주목/);
    assert.match(analyzed, /협력의 필요성을 보도/);
    assert.match(analyzed, /기업별 대응을 분석/);
    assert.match(analyzed, /분석에 사용한 기사 12건/);
    assert.match(analyzed, /선택한 국가의 상세 제목/);
    assert.match(analyzed, /<li>두 번째 보도 관점<\/li>/);
    assert.match(analyzed, /<li>세 번째 보도 관점<\/li>/);
    assert.match(analyzed, /dateTime="2026-09-18T10:00:00\+09:00"/i);
    assert.doesNotMatch(perspectives, /세계 여론|강경 지지/);
    assert.match(renderPerspectives({ data: { ...perspectiveData, countryTones: [] }, issueId: 1 }), /관련 기사가 있는 국가가 없습니다/);
    assert.match(renderPerspectives({ data: perspectiveData, issueId: 1, spot: 'kr' }), /한국 대표 기사/);
    assert.match(renderPerspectives({ data: perspectiveData, issueId: 1, spot: 'kr' }), /조회 시점까지 등록된 국가별 분석이 없습니다/);
    const failedList = renderPerspectives({ data: perspectiveData, issueId: 1, spot: 'kr', analysis: detailResource,
      countryAnalyses: { ...emptyAnalysis, error: new Error('목록 실패') } });
    assert.match(failedList, /분석 요약 다시 시도/);
    assert.match(failedList, /선택한 국가의 상세 제목/);
    assert.match(failedList, /한국 대표 기사/);
    const { default: CountryAnalysis } = await vite.ssrLoadModule('/src/components/panel/IssueCountryAnalysis.jsx');
    const callout = render(CountryAnalysis, { countryName: '한국', resource: detailResource, onClose() {} });
    assert.match(callout, /선택한 국가의 상세 제목/);
    assert.match(callout, /<li>세 번째 보도 관점<\/li>/);
    assert.match(callout, /분석에 사용한 기사 12건/);
    assert.match(callout, /국가 분석 닫기/);
    assert.doesNotMatch(callout, /화면 예시|undefined|분석 시각 정보가 없습니다/);
    for (const Component of [CountryAnalysis, Perspectives]) {
      const props = { countryName: '한국', data: perspectiveData, countryAnalyses: emptyAnalysis, issueId: 1, spot: 'kr' };
      const loading = { ...emptyAnalysis, loading: true };
      const failed = { ...emptyAnalysis, error: new Error('상세 실패') };
      assert.match(render(Component, { ...props, resource: loading, analysis: loading }), /보도 관점을 불러오고 있습니다/);
      assert.match(render(Component, { ...props, resource: failed, analysis: failed }), /분석 결과를 불러오지 못했습니다/);
      assert.match(render(Component, { ...props, resource: emptyAnalysis, analysis: emptyAnalysis }), /조회 시점까지 등록된 국가별 분석이 없습니다/);
    }
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
    assert.match(render(App, {}), /타임머신/);
    assert.equal((render(App, {}).match(/role="application"/g) || []).length, 1);
    const { StageClock, TimeTravelEffects } = await vite.ssrLoadModule('/src/timeMachine/TimeMachine.jsx');
    assert.match(render(StageClock, { asOf: '2026-09-16T16:30:42Z' }), /2026년 9월 17일 1시 30분/);
    assert.doesNotMatch(render(StageClock, { asOf: '2026-09-16T16:30:42Z' }), /그날의 세계|현재의 세계|한국 시간/);
    const travel = render(TimeTravelEffects, {
      trip: { target: '2026-09-10T01:50:00Z' }, progress: .5, reduced: false, onArrive: () => {},
    });
    assert.match(travel, /세계의 시간을 되감는 중/);
    assert.doesNotMatch(travel, /ONE PLANET|A DIFFERENT MOMENT/);
    assert.doesNotMatch(travel, /<dialog|role="application"/);
    const { TimeMachinePicker } = await vite.ssrLoadModule('/src/timeMachine/TimeMachine.jsx');
    const picker = render(TimeMachinePicker, { asOf: '2026-09-10T01:50:00Z' });
    assert.match(picker, /min="2026-09-06"/);
    assert.match(picker, /value="2026-09-10"/);
    assert.match(picker, /다른 날짜를 선택하세요/);
    assert.match(picker, /disabled=""/);
    assert.match(picker, /data-time-machine-door="left"/);
    assert.doesNotMatch(picker, /지금, 현재의 세계를 보고 있어요|시간을 돌려|↶/);
    const { default: Header } = await vite.ssrLoadModule('/src/components/header/HeaderMinimal.jsx');
    const archivedHeader = render(Header, { asOf: '2026-09-10T01:50:00Z', onTimeMachine: () => {} });
    assert.match(archivedHeader, /aria-expanded="false"/);
    assert.match(render(Header, { timeMachineOpen: true, onTimeMachine: () => {} }), /aria-expanded="true"/);
    assert.match(archivedHeader, /현재로/);
    assert.match(archivedHeader, /href="\/\?asOf=2026-09-10T01%3A50%3A00Z"/);
  } finally { await vite.close(); }
});
