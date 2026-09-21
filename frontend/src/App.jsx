import { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import { api } from './data/api.js';
import { useResource } from './data/useResource.js';
import { loadIssueCountryAnalysis } from './data/issueCountryAnalysis.js';
import { issueCountryPerspectives } from './data/issuePerspective.js';
import IssuePerspectives from './components/panel/IssuePerspectives.jsx';
import { articleCard, themeCard, mentionRows, globeTones, fmt, flagOf, scoreOf } from './data/responseAdapters.js';
import { toneRGB, NO_SAMPLE } from './lib/tone.js';
import { countryMetadata, flagImageOf, iso3 } from './data/countries.js';
import { mentionLinks } from './lib/mentionLinks.js';
import HeaderMinimal from './components/header/HeaderMinimal.jsx';
import GlobeThree from './components/globe/GlobeThree.jsx';
import DashboardLayout, { GlobeSlot } from './components/layout/Layouts.jsx';
import CommandPalette, { usePaletteHotkey } from './components/overlay/CommandPalette.jsx';
import { PanelHeading, SubHeading, SectionTitle, BackLink, CountryIdentity, KpiCards, PolicyNote } from './components/panel/PanelChrome.jsx';
import IssueCardList from './components/panel/IssueCardList.jsx';
import { ThemeCardList, ThemeDetailList, ThemeIssueList } from './components/panel/ThemeLists.jsx';
import AttentionPanel, { AttentionList } from './components/panel/AttentionPanel.jsx';
import ArticleFeed, { ResultHead, ArticleFilterBar } from './components/panel/ArticleFeed.jsx';
import ThemeFilterPanel from './components/panel/ThemeFilterPanel.jsx';
import ApiToneScatter from './components/panel/ApiToneScatter.jsx';
import IssueCountryAnalysis from './components/panel/IssueCountryAnalysis.jsx';
import s from './components/panel/panel.module.css';
import NewsPage from './news/NewsPage.jsx';
import PageTransition from './components/layout/PageTransition.jsx';
import { TimeMachinePicker, TimeTravelEffects, StageClock, useTimeTravel } from './timeMachine/TimeMachine.jsx';
import { readAsOf, timeLabel } from './timeMachine/timeMachine.js';
import { PersonalizationProvider, InterestButton } from './personalization/Personalization.jsx';

const HOME = { type: 'dash', title: '글로벌 동향' };
// true로 변경하면 테마 대표 기사의 더 보기 버튼을 복구합니다.
const SHOW_THEME_ARTICLES_MORE = false;
// true로 변경하면 테마에서 진입한 이슈의 기사 더 보기를 복구합니다.
const SHOW_THEME_ISSUE_ARTICLES_MORE = false;

function ResourceState({ resource, children }) {
  if (resource.loading && !resource.data) return <p role="status">데이터를 불러오고 있습니다…</p>;
  if (resource.error) return <div role="alert"><p>{resource.error.message}</p><button type="button" onClick={resource.retry}>다시 시도</button></div>;
  return resource.data == null ? null : children(resource.data);
}
function Empty({ items, children }) {
  return items.length ? children : <p role="status">해당 조건의 데이터가 없습니다.</p>;
}

function issueRankCard(item) {
  const score = Number(item.globalHeatScore);
  return {
    title: item.issueName,
    field: item.fieldName,
    theme: item.themeName,
    count: `${score.toFixed(1)}점`,
    countries: `${fmt(item.countryCount)}개국`,
  };
}

function countryIssueRankCard(item) {
  const score = Number(item.localHeatScore);
  return {
    title: item.issueName,
    field: item.fieldName,
    theme: item.themeName,
    count: `${score.toFixed(1)}점`,
    countries: '국가별 점수',
  };
}


export default function App() {
  return <PersonalizationProvider><AppContent /></PersonalizationProvider>;
}

function AppContent() {
  const [search, setSearch] = useState(() => typeof window === 'undefined' ? '' : window.location.search);
  const [navigationRevision, setNavigationRevision] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [trip, setTrip] = useState(null);
  const [arrival, setArrival] = useState(null);
  const asOf = readAsOf(search);
  useEffect(() => {
    const sync = () => {
      setSearch(window.location.search);
      setNavigationRevision((value) => value + 1);
      setTrip(null);
      setPickerOpen(false);
      setArrival(null);
    };
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  const navigate = (next) => {
    const params = new URLSearchParams(next);
    if (asOf) params.set('asOf', asOf);
    next = params.size ? `?${params}` : '';
    if (next === window.location.search) return;
    window.history.pushState(null, '', `${window.location.pathname}${next}${window.location.hash}`);
    setSearch(next);
  };
  const travel = (target) => {
    if (trip || arrival) return;
    setPickerOpen(false);
    if (new URLSearchParams(search).get('view') === 'news') navigate('');
    setTrip({ target, origin: asOf, departed: Date.now() });
  };
  const arrive = () => { if (trip && !arrival) setArrival(trip); };
  useEffect(() => {
    if (!arrival) return undefined;
    const reveal = setTimeout(() => {
      const params = new URLSearchParams();
      if (arrival.target) params.set('asOf', arrival.target);
      const next = params.size ? `?${params}` : '';
      window.history.pushState(null, '', `${window.location.pathname}${next}`);
      setSearch(next);
      setTrip(null);
    }, 140);
    const finish = setTimeout(() => setArrival(null), 1000);
    return () => { clearTimeout(reveal); clearTimeout(finish); };
  }, [arrival]);
  const leaveTimeMachine = () => { setPickerOpen(false); setTrip(null); setArrival(null); };
  const timeProps = { asOf, onLeaveTimeMachine: leaveTimeMachine, timeMachineOpen: pickerOpen || Boolean(trip), onTimeMachine: () => { if (new URLSearchParams(search).get('view') === 'news') navigate(''); if (!trip && !arrival) setPickerOpen(true); }, onLive: () => travel(null) };
  const route = new URLSearchParams(search).get('view');
  const page = route === 'news' ? <>
    <HeaderMinimal {...timeProps} route="news" showSearch={false} onRoute={(next) => {
      if (next !== 'news') navigate(next === 'country' ? '?view=country' : '');
    }} />
    <NewsPage key={`${asOf || 'live'}:${navigationRevision}`} asOf={asOf} search={search} navigate={navigate} />
  </> : <DashboardApp picker={pickerOpen ? <TimeMachinePicker asOf={asOf} onTravel={travel} /> : null} arrival={Boolean(arrival)} trip={trip} onArrive={arrive} timeProps={timeProps} asOf={asOf} onNews={() => navigate('?view=news&page=1')} initialCountry={route === 'country'} />;
  return <><PageTransition screenKey={route === 'news' ? 'news' : 'dashboard'}>{page}</PageTransition>
  </>;
}

function DashboardApp({ picker, arrival, onNews, initialCountry, asOf, timeProps, trip, onArrive }) {
  const journey = useTimeTravel(trip, onArrive);
  const timeMachineActive = timeProps.timeMachineOpen || Boolean(trip);
  const [history, setHistory] = useState(() => initialCountry
    ? [HOME, { type: 'country', countryCode: 'KR', title: '대한민국' }] : [HOME]);
  const view = history[history.length - 1];
  const [spot, setSpot] = useState(null);
  const [mentionDirection, setMentionDirection] = useState('outgoing');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const panelRef = useRef(null);
  const go = useCallback((next) => {
    setSpot(null);
    setMentionDirection('outgoing');
    setHistory((old) => next.type === 'dash'
      ? [HOME]
      : next.type === 'articles' && old.at(-1).type === 'articles'
        ? [...old.slice(0, -1), next]
        : [...old, next]);
  }, []);
  const goCountry = useCallback((id) => go({ type: 'country', countryCode: id.toUpperCase(), title: countryMetadata.find((c) => c.id === id)?.name || id }), [go]);
  const selectIssueCountry = useCallback((id) => setSpot((old) => old === id ? null : id), []);
  const openPalette = useCallback(() => { if (!trip) setPaletteOpen(true); }, [trip]);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  usePaletteHotkey(openPalette, closePalette);
  useEffect(() => { panelRef.current?.scrollTo({ top: 0 }); setSpot(null); }, [view]);
  const previousTime = useRef(asOf);
  useEffect(() => {
    if (previousTime.current !== asOf) {
      previousTime.current = asOf;
      go(HOME);
    }
  }, [asOf, go]);
  useEffect(() => {
    if (trip) { setPaletteOpen(false); setSpot(null); panelRef.current?.scrollTo({ top: 0 }); }
  }, [trip]);

  const dashboard = useResource(`dashboard:${asOf}`, (signal) => api.dashboard(signal, asOf), asOf ? 0 : 60000);
  const fields = useResource(`fields:${asOf}`, (signal) => api.fields(signal, asOf));
  const country = useResource(view.countryCode ? `country:${asOf}:${view.countryCode}` : null, (signal) => api.country(view.countryCode, signal, asOf));
  const popular = useResource(view.countryCode && ['themes', 'field'].includes(view.type) ? `popular:${asOf}:${view.countryCode}` : null, (signal) => api.popular(view.countryCode, signal, asOf));
  const theme = useResource(view.themeId ? `theme:${asOf}:${view.themeId}:${view.countryCode || 'global'}` : null, (signal) => api.theme(view.themeId, view.countryCode, signal, asOf));
  const issue = useResource(view.issueId ? `issue:${asOf}:${view.issueId}:${view.countryCode || 'global'}` : null, async (signal) => {
    const [detail, overview] = await Promise.all([api.issue(view.issueId, signal, asOf), api.overview(view.issueId, view.countryCode, signal, asOf)]);
    return { ...detail, ...overview };
  });

  const catalog = useMemo(() => (fields.data || []).flatMap((field) => field.themes.map((item) => ({ ...item, fieldId: field.fieldId, fieldName: field.fieldName }))), [fields.data]);
  const globalIssue = view.type === 'issue' && !view.countryCode;
  const countryAnalyses = useResource(view.type === 'issue' ? `country-analyses:${asOf}:${view.issueId}` : null,
    (signal) => api.countryAnalyses(view.issueId, signal, asOf));
  const rankedCountries = useMemo(() => issueCountryPerspectives(issue.error ? {} : issue.data || {}, countryAnalyses.data?.countryAnalyses),
    [issue.data, issue.error, countryAnalyses.data]);
  const issueCards = useMemo(() => globalIssue ? rankedCountries.filter((row) => countryMetadata.some((c) => c.id === row.country.countryCode.toLowerCase())) : [], [globalIssue, rankedCountries]);
  const rows = (issue.data?.countryTones || []).filter((row) => !view.countryCode || row.country.countryCode.toUpperCase() === view.countryCode);
  const selectedCountry = view.type === 'issue' ? countryMetadata.find((item) => item.id === spot) : null;
  const selectedTone = view.type === 'issue' && spot
    ? issue.data?.countryTones?.find((row) => row.country.countryCode.toLowerCase() === spot) : null;
  const analysisToneColor = selectedTone?.toneAvg != null
    ? toneRGB(scoreOf(selectedTone.toneAvg)).join(', ') : NO_SAMPLE.join(', ');
  const analysis = useResource(view.type === 'issue' && spot && issue.data && !issue.error ? `analysis:${asOf}:${view.issueId}:${spot}` : null,
    (signal) => loadIssueCountryAnalysis({
      issueId: view.issueId,
      countryCode: spot,
      asOf,
    }, signal));
  const mapTone = useMemo(() => view.type === 'issue' && issue.data && !issue.error
    ? { name: issue.data.issuePreview.issueTitle, t: globeTones(issue.data.countryTones, view.countryCode) }
    : null,
  [view.type, view.countryCode, issue.data, issue.error]);
  const openTheme = (item) => go({ type: 'theme', title: item.themeName, themeId: item.themeId, countryCode: view.countryCode });
  const openIssue = (item) => {
    const parent = catalog.find((t) => t.themeName === item.themeName);
    go({ type: 'issue', title: item.issueName || item.issueTitle, issueId: item.issueId, themeId: view.themeId || parent?.themeId, countryCode: view.countryCode, fromTheme: view.type === 'theme' });
  };
  const openArticles = () => go({ ...view, type: 'articles', title: '대표 기사' });
  const countryName = country.data?.countryName || countryMetadata.find((c) => c.code === view.countryCode)?.name || view.countryCode;
  const updated = asOf ? `${timeLabel(asOf)} 기준` : dashboard.updatedAt ? `${dashboard.updatedAt.toLocaleTimeString('ko-KR')} 조회` : '';
  const relations = useMemo(() => view.type === 'attention' && !country.error
    && country.data?.countryCode?.toUpperCase() === view.countryCode
    ? mentionLinks(country.data, mentionDirection, countryMetadata) : [],
  [view.type, view.countryCode, country.data, country.error, mentionDirection]);

  let body;
  if (view.type === 'dash') body = <ResourceState resource={dashboard}>{(data) => <div className={s.globalDashboard}>
    <PanelHeading title="글로벌 동향" updated={updated} />
    <KpiCards items={[{ label: '전체 수집 기사', value: fmt(data.totalArticleCount), unit: '건' }, { label: '최근 24시간 수집 기사', value: fmt(data.recent24ArticleCount), unit: '건' }]} />
    <SectionTitle title={asOf ? '그날의 이슈 TOP 5' : '실시간 이슈 TOP 5'}
      note="국가별 보도 강도·확산도 종합 점수 순"
      help={asOf ? '선택 시점 직전 24시간을 기준으로 집계합니다.' : '핫이슈 점수는 5분마다 갱신됩니다.'} />
    <Empty items={data.globalIssues}><IssueCardList issues={data.globalIssues.map(issueRankCard)} onSelect={(index) => openIssue(data.globalIssues[index])} /></Empty>
  </div>}</ResourceState>;
  else if (view.type === 'country') body = <ResourceState resource={country}>{(data) => <div className={s.countryDashboard}>
    <CountryIdentity flag={flagOf(data.countryCode)}
      flagImage={flagImageOf(data.countryCode)}
      flagClass={countryMetadata.find((item) => item.code === data.countryCode.toUpperCase())?.flagClass}
      name={data.countryName} />
    <KpiCards items={[{ label: '최근 24시간 수집 기사', value: fmt(data.todayArticleCount), unit: '건' }, { label: '기사량 세계 순위', value: fmt(data.globalRank), unit: '위' }]} />
    <section className={s.countrySection} aria-label="핫이슈">
    <SectionTitle title="핫이슈 TOP 5" note="보도 비중·증가세·매체 다양성 기준" help={asOf ? '선택 시점 직전 최신 점수 스냅샷을 기준으로 집계합니다.' : '핫이슈 점수는 5분마다 갱신됩니다.'} />
    <Empty items={data.countryIssues || []}><IssueCardList issues={(data.countryIssues || []).map(countryIssueRankCard)} onSelect={(index) => openIssue(data.countryIssues[index])} /></Empty>
    </section>
    <section className={s.countrySection} aria-label="인기 테마">
    <SectionTitle title="인기 테마" action={{ label: '전체 보기 →', onClick: () => go({ type: 'themes', title: `${data.countryName} 인기 테마`, countryCode: view.countryCode }) }} />
    <Empty items={data.popularThemes}><ThemeCardList themes={data.popularThemes.map(themeCard)} onSelect={(index) => openTheme(data.popularThemes[index])} /></Empty>
    </section>
    <section className={s.countrySection} aria-label="많이 언급한 국가">
    <SectionTitle title="많이 언급한 국가" action={{ label: '자세히 보기 →', onClick: () => go({ type: 'attention', title: '국가 관심도', countryCode: view.countryCode }) }} />
    <Empty items={data.sourceMentions}><AttentionList rows={mentionRows(data.sourceMentions)} /></Empty>
    </section>
  </div>}</ResourceState>;
  else if (view.type === 'theme') body = <ResourceState resource={theme}>{(data) => <>
    <div className={s.themeHeading}>
    <SubHeading title={data.themeName} desc={data.themeDescription} />
    <div className={s.themeHeadingAction}>
    <InterestButton kind="themes" id={view.themeId} name={data.themeName} />
    </div>
    </div>
    {view.countryCode && <PolicyNote>주요 이슈와 대표 기사는 {countryName} 발행 기사 기준입니다.</PolicyNote>}
    <SectionTitle title="주요 이슈" note={`${asOf ? '선택 시점 직전' : '최근'} 24시간 · ${view.countryCode ? countryName : '전 세계'} 기사량 순`} />
    <Empty items={data.primaryIssues}><ThemeIssueList issues={data.primaryIssues.map((item) => ({ title: item.issueTitle }))} onSelect={(index) => openIssue(data.primaryIssues[index])} /></Empty>
    <SectionTitle title={view.countryCode ? `${countryName} 대표 기사` : '대표 기사'}
      note={asOf ? '선택 시점 직전 24시간 · 테마 유사도순' : '최근 24시간 · 테마 유사도순'}
      action={SHOW_THEME_ARTICLES_MORE ? { label: '더 보기 →', onClick: openArticles } : undefined} />
    <ArticleFeed articles={data.representArticles.slice(0, 3).map(articleCard)} />
  </>}</ResourceState>;
  else if (globalIssue) body = <ResourceState resource={issue}>{(data) => <IssuePerspectives data={data} issueId={view.issueId} asOf={asOf}
    countryAnalyses={countryAnalyses} spot={spot} onSelectCountry={selectIssueCountry} />}</ResourceState>;
  else if (view.type === 'issue') body = <ResourceState resource={issue}>{(data) => <>
    <SubHeading title={data.issuePreview.issueTitle} desc={data.issuePreview.themeTitle} />
    <SectionTitle title={view.countryCode ? `${countryName}의 논조` : '국가별 논조'} note="최근 24시간 발행 기사 기준" />
    <ApiToneScatter rows={rows} spot={spot} onSelectCountry={selectIssueCountry} />
    <SectionTitle title={view.countryCode ? `${countryName} 대표 기사` : '대표 기사 · 전 세계'}
      action={!view.fromTheme || SHOW_THEME_ISSUE_ARTICLES_MORE ? { label: '더 보기 →', onClick: openArticles } : undefined} />
    <ArticleFeed articles={data.representArticles.slice(0, 3).map(articleCard)} />
  </>}</ResourceState>;
  else if (view.type === 'attention') body = <ResourceState resource={country}>{(data) => <AttentionScreen data={data} direction={mentionDirection} onDirection={setMentionDirection} linkCount={relations.length} />}</ResourceState>;
  else if (view.type === 'themes' || view.type === 'field') body = <ResourceState resource={view.countryCode ? popular : fields}>{() => {
    const list = view.countryCode ? (popular.data?.popularThemes || []) : catalog;
    const grouped = [...new Set(list.map((item) => item.fieldName))];
    return <><SubHeading title={view.title} desc={view.countryCode ? '최근 24시간 · 상위 10개 테마' : undefined} />
      <Empty items={list}>{grouped.filter((name) => !view.fieldName || name === view.fieldName).map((name) => {
        const items = list.filter((item) => item.fieldName === name);
        return <div key={name}><SectionTitle title={name} action={view.type === 'field' ? undefined : { label: '이 분야 보기 →', onClick: () => go({ type: 'field', title: name, fieldName: name, countryCode: view.countryCode }) }} />
          <ThemeDetailList themes={items.map(themeCard)} onSelect={(index) => openTheme(items[index])} /></div>;
      })}</Empty></>;
  }}</ResourceState>;
  else if (view.type === 'articles') body = <ArticlesScreen key={`${view.countryCode || ''}:${view.themeId || ''}:${view.issueId || ''}`}
    view={view} catalog={catalog} fieldsResource={fields} countryResource={country} themeResource={theme} issueResource={issue} go={go} />;

  return <><DashboardLayout panelRef={panelRef} timeTravel={timeMachineActive} arrival={arrival} overlay={<>{picker}{trip && <TimeTravelEffects trip={trip} {...journey} onArrive={onArrive} />}</>}
    header={<HeaderMinimal {...timeProps} route={view.countryCode ? 'country' : 'global'} onRoute={(route) => { timeProps.onLeaveTimeMachine(); if (route === 'news') onNews(); else if (route === 'global') go(HOME); else goCountry(view.countryCode?.toLowerCase() || 'kr'); }} onSearch={openPalette} />}
    stage={<GlobeSlot><GlobeThree countries={countryMetadata} iso3={iso3} tone={mapTone} minSample={null} focus={spot || view.countryCode?.toLowerCase() || issueCards[0]?.country.countryCode.toLowerCase()}
      issueCards={timeMachineActive ? [] : issueCards} selectedIssueCountry={spot}
      onSelectIssueCountry={selectIssueCountry}
      globalIssueView={globalIssue}
      satelliteDemo={!asOf && !timeMachineActive}
      timeMachineActive={timeMachineActive}
      timeTravel={trip ? (journey.reduced ? 0 : journey.progress) : null}
      timeTravelDirection={trip && trip.target === null ? 1 : -1}
      calloutCountry={timeMachineActive ? null : selectedCountry?.id || null}
      calloutToneColor={analysisToneColor}
      callout={selectedCountry ? <IssueCountryAnalysis countryName={selectedCountry.name}
        toneColor={analysisToneColor} resource={analysis} onClose={() => setSpot(null)} /> : null}
      countryClickHint="클릭하면 국가 분석 보기"
      onGlobeMove={view.type === 'issue' && spot ? () => setSpot(null) : undefined}
      mentionRelations={timeMachineActive ? [] : relations} spinControl={!timeMachineActive} onOpenCountry={view.type === 'issue' ? selectIssueCountry : goCountry} />
      {!picker && <StageClock asOf={asOf} travelDate={journey.date} centered={Boolean(trip)} />}
      </GlobeSlot>}
    panel={<div className={s.panelContent}>{history.length > 1 && <div className={s.panelNav}>
      <BackLink onClick={() => setHistory((old) => old.slice(0, -1))}>← 이전 화면</BackLink>
    </div>}{body}</div>} />
    <CommandPalette open={paletteOpen} onClose={closePalette} quick={countryMetadata.map((item) => ({ flag: item.flag, flagImage: item.flagImage, flagClass: item.flagClass, name: item.name }))}
      onSelect={(name) => goCountry(countryMetadata.find((item) => item.name === name).id)} /></>;
}

function AttentionScreen({ data, direction, onDirection, linkCount }) {
  return <><SubHeading title={`${data.countryName}의 국가 관심도`} desc="최근 24시간 기사 내 국가명 언급 비율입니다. 방향별 최대 10개국을 표시합니다." />
    <PolicyNote>{direction === 'outgoing' ? '청록색 흐르는 점선: 선택 국가 → 언급한 국가' : '주황색 흐르는 점선: 언급한 국가 → 선택 국가'} · 지구본에 상위 10개국 중 {linkCount}개 연결 표시. 좌표가 없는 국가는 목록에서만 표시합니다. 지구본을 드래그하면 반대편 연결도 볼 수 있습니다.</PolicyNote>
    <AttentionPanel country={data.countryName} countryCode={data.countryCode} direction={direction} onDirection={onDirection}
      rows={mentionRows(direction === 'outgoing' ? data.sourceMentions : data.targetMentions)} /></>;
}

function ArticlesScreen({ view, catalog, fieldsResource, countryResource, themeResource, issueResource, go }) {
  const [tone, setTone] = useState('all');
  const countryName = countryResource.data?.countryName || countryMetadata.find((c) => c.code === view.countryCode)?.name || view.countryCode;
  const resource = view.issueId ? issueResource : view.themeId ? themeResource : countryResource;
  const selected = catalog.find((item) => item.themeId === view.themeId);
  const selectTheme = (item) => go({ type: 'articles', title: '대표 기사', countryCode: view.countryCode, themeId: item?.themeId });
  return <><SubHeading title="대표 기사" desc={view.countryCode ? countryName : '전 세계'} />
    <ResourceState resource={fieldsResource}>{() => <ThemeFilterPanel catalog={catalog.map(themeCard)}
      fields={[...new Set(catalog.map((item) => item.fieldName))]} totalLabel={String(catalog.length)}
      selectedTheme={selected ? themeCard(selected) : null}
      onSelectCatalog={(index) => selectTheme(catalog[index])} />}</ResourceState>
    <ArticleFilterBar tone={tone} onTone={setTone} />
    {!view.issueId && !view.themeId && !view.countryCode ? <p>테마를 선택해 주세요.</p> : <ResourceState resource={resource}>{(data) => {
      const articles = data.representArticles.map(articleCard).filter((article) => tone === 'all' || article.tone === tone);
      return <><ResultHead title="검색 결과" count={`${articles.length}건`} /><ArticleFeed articles={articles} /></>;
    }}</ResourceState>}
  </>;
}
