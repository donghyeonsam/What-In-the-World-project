import { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import { api } from './data/api.js';
import { useResource } from './data/useResource.js';
import { articleCard, themeCard, mentionRows, globeTones, fmt, flagOf } from './data/responseAdapters.js';
import { countryMetadata, iso3 } from './data/countries.js';
import HeaderMinimal from './components/header/HeaderMinimal.jsx';
import GlobeThree from './components/globe/GlobeThree.jsx';
import DashboardLayout, { StageHead, GlobeSlot, StageFoot } from './components/layout/Layouts.jsx';
import CommandPalette, { usePaletteHotkey } from './components/overlay/CommandPalette.jsx';
import { PanelTopline, PanelHeading, SubHeading, SectionTitle, BackLink, TaxonomyPath, CountryIdentity, KpiCards, PolicyNote } from './components/panel/PanelChrome.jsx';
import IssueCardList from './components/panel/IssueCardList.jsx';
import { ThemeCardList, ThemeDetailList, ThemeIssueList } from './components/panel/ThemeLists.jsx';
import AttentionPanel, { AttentionList } from './components/panel/AttentionPanel.jsx';
import ArticleFeed, { ArticlePreviewList, ResultHead, ArticleFilterBar } from './components/panel/ArticleFeed.jsx';
import ThemeFilterPanel from './components/panel/ThemeFilterPanel.jsx';
import ApiToneScatter from './components/panel/ApiToneScatter.jsx';
import s from './components/panel/panel.module.css';

const HOME = { type: 'dash', title: '글로벌 동향' };

function ResourceState({ resource, children }) {
  if (resource.loading && !resource.data) return <p role="status">데이터를 불러오고 있습니다…</p>;
  if (resource.error) return <div role="alert"><p>{resource.error.message}</p><button type="button" onClick={resource.retry}>다시 시도</button></div>;
  return resource.data == null ? null : children(resource.data);
}
function Empty({ items, children }) {
  return items.length ? children : <p role="status">해당 조건의 데이터가 없습니다.</p>;
}

export default function App() {
  const [history, setHistory] = useState([HOME]);
  const view = history[history.length - 1];
  const [mapMode, setMapMode] = useState('tone');
  const [spot, setSpot] = useState(null);
  const [pick, setPick] = useState(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const panelRef = useRef(null);
  const go = useCallback((next) => {
    setSpot(null); setPick(null);
    setHistory((old) => next.type === 'dash' ? [HOME] : next.type === 'articles' && old.at(-1).type === 'articles' ? [...old.slice(0, -1), next] : [...old, next]);
  }, []);
  const goCountry = useCallback((id) => go({ type: 'country', countryCode: id.toUpperCase(), title: countryMetadata.find((c) => c.id === id)?.name || id }), [go]);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  usePaletteHotkey(openPalette, closePalette);
  useEffect(() => { panelRef.current?.scrollTo({ top: 0 }); setSpot(null); setPick(null); }, [view]);

  const dashboard = useResource('dashboard', api.dashboard, 60000);
  const fields = useResource('fields', api.fields);
  const country = useResource(view.countryCode ? `country:${view.countryCode}` : null, (signal) => api.country(view.countryCode, signal));
  const popular = useResource(view.countryCode && ['themes', 'field'].includes(view.type) ? `popular:${view.countryCode}` : null, (signal) => api.popular(view.countryCode, signal));
  const theme = useResource(view.themeId ? `theme:${view.themeId}` : null, (signal) => api.theme(view.themeId, signal));
  const issue = useResource(view.issueId ? `issue:${view.issueId}` : null, async (signal) => {
    const [detail, overview] = await Promise.all([api.issue(view.issueId, signal), api.overview(view.issueId, signal)]);
    return { ...detail, ...overview };
  });

  const catalog = useMemo(() => (fields.data || []).flatMap((field) => field.themes.map((item) => ({ ...item, fieldId: field.fieldId, fieldName: field.fieldName }))), [fields.data]);
  const rows = (issue.data?.countryTones || []).filter((row) => !view.countryCode || row.country.countryCode.toUpperCase() === view.countryCode);
  const tone = useMemo(() => issue.data && !issue.error && view.issueId && mapMode === 'tone'
    ? { name: issue.data.issuePreview.issueTitle, t: globeTones(issue.data.countryTones, view.countryCode) } : null,
  [issue.data, issue.error, view.issueId, view.countryCode, mapMode]);
  const openTheme = (item) => go({ type: 'theme', title: item.themeName, themeId: item.themeId, countryCode: view.countryCode });
  const openIssue = (item) => {
    const parent = catalog.find((t) => t.themeName === item.themeName);
    go({ type: 'issue', title: item.issueName || item.issueTitle, issueId: item.issueId, themeId: view.themeId || parent?.themeId, countryCode: view.countryCode });
  };
  const openArticles = () => go({ ...view, type: 'articles', title: '대표 기사' });
  const countryName = country.data?.countryName || countryMetadata.find((c) => c.code === view.countryCode)?.name || view.countryCode;
  const updated = dashboard.updatedAt ? `${dashboard.updatedAt.toLocaleTimeString('ko-KR')} 조회` : '';

  let body;
  if (view.type === 'dash') body = <ResourceState resource={dashboard}>{(data) => <>
    <PanelTopline label="글로벌 요약" /><PanelHeading title="글로벌 동향" desc="세계 뉴스의 변화를 한눈에 확인하세요." updated={updated} />
    <KpiCards items={[{ label: '전체 수집 기사', value: fmt(data.totalArticleCount), unit: '건' }, { label: '최근 24시간 수집 기사', value: fmt(data.recent24ArticleCount), unit: '건' }]} />
    <SectionTitle title="실시간 이슈 TOP 5" note="최근 24시간 발행 기사량 순" />
    <Empty items={data.globalIssues}><IssueCardList issues={data.globalIssues.map((item) => ({ title: item.issueName, field: item.fieldName, theme: item.themeName, count: `${fmt(item.articleCount)}건` }))} onSelect={(index) => openIssue(data.globalIssues[index])} /></Empty>
    <SectionTitle title="테마 탐색" action={{ label: '분야별 테마 보기 →', onClick: () => go({ type: 'themes', title: '분야별 테마' }) }} />
    <PolicyNote>수집 현황은 1분마다 갱신됩니다.</PolicyNote>
  </>}</ResourceState>;
  else if (view.type === 'country') body = <ResourceState resource={country}>{(data) => <>
    <PanelTopline label="국가 분석" /><CountryIdentity flag={flagOf(data.countryCode)} name={data.countryName} meta="최근 24시간 수집 현황" />
    <KpiCards items={[{ label: '최근 24시간 수집 기사', value: fmt(data.todayArticleCount), unit: '건' }, { label: '기사량 세계 순위', value: fmt(data.globalRank), unit: '위' }]} />
    <SectionTitle title="인기 테마" action={{ label: '전체 보기 →', onClick: () => go({ type: 'themes', title: `${data.countryName} 인기 테마`, countryCode: view.countryCode }) }} />
    <Empty items={data.popularThemes}><ThemeCardList themes={data.popularThemes.map(themeCard)} onSelect={(index) => openTheme(data.popularThemes[index])} /></Empty>
    <SectionTitle title={`${data.countryName}이 많이 언급한 국가`} action={{ label: '자세히 보기 →', onClick: () => go({ type: 'attention', title: '국가 관심도', countryCode: view.countryCode }) }} />
    <Empty items={data.sourceMentions}><AttentionList rows={mentionRows(data.sourceMentions)} /></Empty>
    <SectionTitle title="대표 기사" action={{ label: '논조별 보기 →', onClick: openArticles }} />
    <Empty items={data.representArticles}><ArticlePreviewList articles={data.representArticles.map(articleCard)} /></Empty>
  </>}</ResourceState>;
  else if (view.type === 'theme') body = <ResourceState resource={theme}>{(data) => <>
    <PanelTopline label={view.countryCode ? `${countryName}에서 선택한 테마` : '테마 상세'} range="전체 기간" />
    <SubHeading title={data.themeName} desc={data.themeDescription || '테마의 주요 이슈와 대표 기사를 확인하세요.'} />
    {view.countryCode && <PolicyNote>테마의 주요 이슈와 대표 기사는 전 세계 기준입니다. 이슈를 선택하면 {countryName}의 논조만 표시합니다.</PolicyNote>}
    <SectionTitle title="주요 이슈" note="전 세계 기사량 순 · 최대 10개" />
    <Empty items={data.primaryIssues}><ThemeIssueList issues={data.primaryIssues.map((item) => ({ title: item.issueTitle }))} onSelect={(index) => openIssue(data.primaryIssues[index])} /></Empty>
    <SectionTitle title="대표 기사" action={{ label: '더 보기 →', onClick: openArticles }} />
    <ArticleFeed articles={data.representArticles.slice(0, 3).map(articleCard)} />
  </>}</ResourceState>;
  else if (view.type === 'issue') body = <ResourceState resource={issue}>{(data) => <>
    <PanelTopline label={view.countryCode ? `${countryName} · 이슈 논조` : '글로벌 이슈 논조'} />
    <SubHeading title={data.issuePreview.issueTitle} desc={data.issuePreview.themeTitle} />
    <KpiCards items={[{ label: '전 세계 관련 기사 · 전체 기간', value: fmt(data.issueInfo.articleCount), unit: '건' }, { label: '보도 국가 · 전체 기간', value: fmt(data.issueInfo.countryCount), unit: '개국' }]} />
    <SectionTitle title={view.countryCode ? `${countryName}의 논조` : '국가별 논조'} note="최근 24시간 발행 기사 기준" />
    <ApiToneScatter rows={rows} spot={spot} onSelectCountry={(id) => setSpot((old) => old === id ? null : id)} />
    <SectionTitle title="이 이슈의 대표 기사 · 전 세계" action={{ label: '더 보기 →', onClick: openArticles }} />
    <ArticleFeed articles={data.representArticles.slice(0, 3).map(articleCard)} />
  </>}</ResourceState>;
  else if (view.type === 'attention') body = <ResourceState resource={country}>{(data) => <AttentionScreen key={data.countryCode} data={data} />}</ResourceState>;
  else if (view.type === 'themes' || view.type === 'field') body = <ResourceState resource={view.countryCode ? popular : fields}>{() => {
    const list = view.countryCode ? (popular.data?.popularThemes || []) : catalog;
    const grouped = [...new Set(list.map((item) => item.fieldName))];
    return <><PanelTopline label={view.countryCode ? `${countryName} · 테마 분석` : '테마 분석'} />
      <SubHeading title={view.title} desc={view.countryCode ? '최근 24시간 인기 테마 최대 10개와 시간별 기사량입니다.' : '분야별 테마를 선택해 관련 이슈를 확인하세요.'} />
      <Empty items={list}>{grouped.filter((name) => !view.fieldName || name === view.fieldName).map((name) => {
        const items = list.filter((item) => item.fieldName === name);
        return <div key={name}><SectionTitle title={name} action={view.type === 'field' ? undefined : { label: '이 분야 보기 →', onClick: () => go({ type: 'field', title: name, fieldName: name, countryCode: view.countryCode }) }} />
          <ThemeDetailList themes={items.map(themeCard)} onSelect={(index) => openTheme(items[index])} /></div>;
      })}</Empty></>;
  }}</ResourceState>;
  else if (view.type === 'articles') body = <ArticlesScreen key={`${view.countryCode || ''}:${view.themeId || ''}:${view.issueId || ''}`}
    view={view} catalog={catalog} fieldsResource={fields} countryResource={country} themeResource={theme} issueResource={issue} go={go} />;

  return <><DashboardLayout panelRef={panelRef}
    header={<HeaderMinimal route={view.countryCode ? 'country' : 'global'} onRoute={(route) => route === 'global' ? go(HOME) : goCountry(view.countryCode?.toLowerCase() || pick || 'kr')} onSearch={openPalette} status="뉴스 분석" />}
    stage={<><StageHead eyebrow={view.countryCode ? `국가 분석 · ${countryName}` : 'Global News'} title={view.type === 'dash' ? <>전 세계 뉴스의 <em>흐름</em>을<br />한눈에 확인하세요</> : view.title}
      desc={view.issueId ? (view.countryCode ? `${countryName}의 논조만 표시합니다.` : '최근 24시간 국가별 논조를 확인하세요.') : '나라를 한 번 누르면 표시하고, 두 번 누르면 국가 분석을 엽니다.'}
      mode={mapMode} onMode={setMapMode} toneAvailable={Boolean(view.issueId)} />
      <GlobeSlot><GlobeThree countries={countryMetadata} iso3={iso3} tone={tone} minSample={30} focus={spot || view.countryCode?.toLowerCase()} highlight={pick}
        spinControl={false} onSelectCountry={(id) => setPick((old) => old === id ? null : id)} onOpenCountry={goCountry} /></GlobeSlot>
      <StageFoot toneOn={Boolean(tone)} minSample={30} updated={view.type === 'dash' ? updated : ''} /></>}
    panel={<>{history.length > 1 && <div className={s.panelNav}><BackLink onClick={() => setHistory((old) => old.slice(0, -1))}>← {history[history.length - 2].title}</BackLink>
      <TaxonomyPath items={history.map((item, index) => ({ label: '', value: item.title, onClick: index === history.length - 1 ? undefined : () => setHistory((old) => old.slice(0, index + 1)) }))} /></div>}{body}</>} />
    <CommandPalette open={paletteOpen} onClose={closePalette} quick={countryMetadata.map((item) => ({ flag: item.flag, name: item.name, count: item.code }))}
      onSelect={(name) => goCountry(countryMetadata.find((item) => item.name === name).id)} /></>;
}

function AttentionScreen({ data }) {
  const [direction, setDirection] = useState('outgoing');
  return <><PanelTopline label="국가 관심도" /><SubHeading title={`${data.countryName}의 국가 관심도`} desc="최근 24시간 기사 내 국가명 언급 비율입니다. 방향별 상위 4개국을 표시합니다." />
    <AttentionPanel country={data.countryName} flag={flagOf(data.countryCode)} direction={direction} onDirection={setDirection}
      rows={mentionRows(direction === 'outgoing' ? data.sourceMentions : data.targetMentions)} /></>;
}

function ArticlesScreen({ view, catalog, fieldsResource, countryResource, themeResource, issueResource, go }) {
  const [tone, setTone] = useState('all');
  const resource = view.issueId ? issueResource : view.themeId ? themeResource : countryResource;
  const selected = catalog.find((item) => item.themeId === view.themeId);
  const selectTheme = (item) => go({ type: 'articles', title: '대표 기사', countryCode: view.countryCode, themeId: item?.themeId });
  return <><PanelTopline label="기사 탐색" range={view.issueId || view.themeId ? '전체 기간' : '최근 24시간 수집'} /><SubHeading title="대표 기사" desc={view.issueId || view.themeId ? '전 세계 대표 기사 최대 10건에서 논조를 선택해 확인하세요.' : '선택 국가의 대표 기사에서 논조를 선택해 확인하세요.'} />
    <ResourceState resource={fieldsResource}>{() => <ThemeFilterPanel quickThemes={catalog.slice(0, 5).map(themeCard)} catalog={catalog.map(themeCard)}
      fields={[...new Set(catalog.map((item) => item.fieldName))]} totalLabel={String(catalog.length)}
      selectedIndex={selected && catalog.indexOf(selected) < 5 ? catalog.indexOf(selected) : null} selectedTheme={selected ? themeCard(selected) : null}
      onSelectQuick={(index) => selectTheme(index == null ? null : catalog[index])} onSelectCatalog={(index) => selectTheme(catalog[index])} />}</ResourceState>
    <ArticleFilterBar tone={tone} onTone={setTone} />
    {!view.issueId && !view.themeId && !view.countryCode ? <p>테마를 선택해 주세요.</p> : <ResourceState resource={resource}>{(data) => {
      const articles = data.representArticles.map(articleCard).filter((article) => tone === 'all' || article.tone === tone);
      return <><ResultHead title={view.issueId ? '이슈 대표 기사' : selected?.themeName || '국가 대표 기사'} count={`${articles.length}건`} /><ArticleFeed articles={articles} /></>;
    }}</ResourceState>}
  </>;
}
