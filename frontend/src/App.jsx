import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  COUNTRIES, ISSUES, THEMES, FIELDS, MIN_SAMPLE, PIN_CITIES, ISO3,
  C, C_NAME, T, T_NAME, I, FIELD, FIELD_NAME,
  ARTICLES, issuesOfTheme, articlesOfTheme, themesOfField, issuesOfField,
  countryToneOf, hasSample,
  attentionRows, attentionLead, toneOverlayOf, validateModel,
} from './data/model.js';
import {
  toIssueCard, toThemeCard, toThemeIssue, toArticleCard,
  themeCatalog, themeIdFromCatalog, pinsOfCountry, countryThemeRows, fmt,
} from './data/adapters.js';
import { toneLabel3 } from './lib/tone.js';
import { josaRo } from './lib/format.js';
import {
  HOME, levelOf, titleOf, backOf, canGoBack, crumbsOf,
  toIssue, toTheme, toField, toCountry, toDash, openAside,
} from './navigation.js';

import HeaderMinimal from './components/header/HeaderMinimal.jsx';
import GlobeThree from './components/globe/GlobeThree.jsx';
import DashboardLayout, { StageHead, GlobeSlot, StageFoot } from './components/layout/Layouts.jsx';
import ToneLegend from './components/overlay/ToneLegend.jsx';
import CommandPalette, { usePaletteHotkey } from './components/overlay/CommandPalette.jsx';
import {
  PanelTopline, PanelHeading, SubHeading, SectionTitle, BackLink,
  TaxonomyPath, CountryIdentity, Divider, KpiCards,
  PolicyNote, LiveDot,
} from './components/panel/PanelChrome.jsx';
import IssueCardList from './components/panel/IssueCardList.jsx';
import { ThemeCardList, ThemeDetailList, ThemeIssueList } from './components/panel/ThemeLists.jsx';
import AttentionPanel, { AttentionList } from './components/panel/AttentionPanel.jsx';
import ArticleFeed, { ArticlePreviewList, ResultHead, ArticleFilterBar } from './components/panel/ArticleFeed.jsx';
import ThemeFilterPanel from './components/panel/ThemeFilterPanel.jsx';
import ToneScatter from './components/panel/ToneScatter.jsx';
import IssueHero, { SummaryBox } from './components/panel/IssueHero.jsx';
import s from './components/panel/panel.module.css';

const CATALOG = themeCatalog();
const TODAY_TOTAL = COUNTRIES.reduce((sum, c) => sum + c.today, 0);
const GRAND_TOTAL = 1284920;

/* 개발 중에만 모델 검증 결과를 콘솔에 남긴다 (결정표 1-4) */
if (import.meta.env.DEV) {
  const { err, warn } = validateModel();
  const style = err.length ? 'color:#d94b57;font-weight:700' : 'color:#16845b';
  console.groupCollapsed(`%c모델 검증 — 오류 ${err.length} · 경고 ${warn.length}`, style);
  err.forEach((m) => console.error(m));
  warn.forEach((m) => console.warn(m));
  console.groupEnd();
}

export default function App() {
  /* 화면 상태는 좌표 하나뿐이다. 이동·뒤로가기 규칙은 navigation.js에 있다. */
  const [view, setView] = useState(HOME);
  const [mapMode, setMapMode] = useState('tone');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [today, setToday] = useState(TODAY_TOTAL);

  /* 지구본이 지금 바라보는 나라.
     화면 좌표가 아니라 카메라 상태다 — 스크롤 위치와 같은 급이라 navigation.js에 넣지 않았다.
     목록에서 나라를 누르면 화면은 그대로 두고 지구본만 그 나라로 돌린다(같은 나라를 다시 누르면 해제).
     화면을 옮기면(go) 카메라도 새 화면 기준으로 돌아가야 하므로 같이 비운다.

     시점은 view.country를 이긴다(`spot ?? view.country`). 국가 분석에서 테마·이슈로 내려오면
     country 칸은 뒤로가기 사다리 때문에 그대로 차 있는데, 그게 시점을 이기면 그 경로로 들어온
     이슈 화면에서만 논조 목록 클릭이 먹지 않는다 — 같은 화면이 들어온 길에 따라 다르게 움직이는 셈이다.
     시점을 풀면(토글 해제) focus가 다시 view.country로 떨어져 원래 보던 나라로 되돌아간다. */
  const [spot, setSpot] = useState(null);

  /* 지구본을 한 번 누른 나라 — 지구본에 표시만 한다.
     화면 좌표가 아니라 지구본 상태다. 패널은 어느 화면에서도 손대지 않는다.
     국가에 대한 정보는 국가 분석 화면 하나가 맡기 때문이다(navigation.js 참고).
     여기서 고른 나라는 헤더 '국가 분석' 탭이 들어갈 기본값이 된다. */
  const [pick, setPick] = useState(null);

  const go = useCallback((next) => {
    setSpot(null);
    setPick(null);
    setView(next);
  }, []);
  const spotCountry = useCallback((id) => setSpot((cur) => (cur === id ? null : id)), []);
  const pickCountry = useCallback((id) => setPick((cur) => (cur === id ? null : id)), []);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  usePaletteHotkey(openPalette, closePalette);

  /* 모니터링이 주인공이므로(결정표 0), 수집 카운터는 계속 오른다 */
  useEffect(() => {
    const id = setInterval(() => setToday((t) => t + Math.floor(Math.random() * 7) + 1), 2600);
    return () => clearInterval(id);
  }, []);

  /* ── 지구본 ──
     칠하는 기준은 "가장 안쪽 좌표가 이슈인가"다.
     국가·테마에 머물 때는 채색을 끄고 톤을 패널 배경으로 넘긴다(결정표 4-1). */
  const toneAvailable = Boolean(view.issueId);
  const toneOn = toneAvailable && mapMode === 'tone';
  const globeTone = toneOn ? toneOverlayOf(view.issueId) : null;

  /* 패널 배경 톤 (결정표 4-1) — 국가 분석 화면에서만 칠한다.
     그 나라의 전반 논조를 색으로 말한다. 지구본을 다시 칠하는 대신 배경으로 옮기는 이유는,
     지도는 '어디'를 말하고 배경은 '지금 보고 있는 이 화면의 분위기'를 말하기 때문이다.

     예전에는 국가 필터(scope) × 이슈·테마·분야 조합으로도 칠했다. 필터를 없앤 뒤로
     그 조합이 아예 없다 — 국가와 이슈를 겹쳐 보는 자리는 이슈 화면의 국가별 논조 목록이다. */
  const panelTone = useMemo(() => {
    if (!view.country) return null;
    const { s: avg, n } = countryToneOf(view.country);
    if (!n) return null;
    return avg > 0.18 ? 'pos' : avg < -0.18 ? 'neg' : 'neu';
  }, [view]);

  const stage = useMemo(() => {
    if (view.issueId) {
      const iss = I(view.issueId);
      return {
        eyebrow: `이슈 · ${T_NAME(iss.theme)}`,
        title: iss.title,
        desc: `${Object.keys(iss.tone).length}개국이 다뤘고 기사 ${fmt(iss.n)}건입니다. 지구본 색이 나라별 논조, 보라색은 표본 부족입니다. 아래 목록에서 나라를 누르면 지구본이 그 나라로 돕니다.`,
      };
    }
    if (view.themeId) {
      const t = T(view.themeId);
      return {
        eyebrow: `테마 · ${FIELD_NAME(t.field)}`,
        title: t.name,
        desc: `이슈 ${t.issueCount}개 · 표본 ${fmt(t.n)}건. 이슈를 하나 고르면 지구본이 나라별 논조로 칠해집니다.`,
      };
    }
    if (view.fieldId) {
      const themes = themesOfField(view.fieldId);
      const issues = issuesOfField(view.fieldId);
      return {
        eyebrow: '분야',
        title: FIELD_NAME(view.fieldId),
        desc: `테마 ${themes.length}개, 이슈 ${issues.length}개가 이 분야에 묶여 있습니다. 테마를 골라 좁혀 들어가세요.`,
      };
    }
    if (view.country) {
      const c = C(view.country);
      return {
        eyebrow: '국가 분석',
        title: (
          <>
            {c.flag} <em>{c.name}</em> 수집 피드
          </>
        ),
        desc: `${c.src} · 오늘 ${fmt(c.today)}건 수집. 톤은 지구본 대신 오른쪽 패널 배경으로 표시합니다.`,
      };
    }
    return {
      eyebrow: 'Orbital View · 7 Regions',
      title: (
        <>
          전 세계 뉴스가 <em>실시간</em>으로
          <br />
          수집되고 있습니다
        </>
      ),
      desc: '나라를 한 번 누르면 지구본에 그 나라가 표시되고, 두 번 누르면 국가 분석으로 넘어갑니다.',
    };
  }, [view]);

  return (
    <>
      <DashboardLayout
        panelTone={panelTone}
        header={
          <HeaderMinimal
            route={view.country ? 'country' : 'global'}
            onRoute={(r) => go(r === 'global' ? toDash() : toCountry(view, view.country ?? pick ?? 'kr'))}
            onSearch={openPalette}
            status={`${COUNTRIES.length}개국 수집 중`}
          />
        }
        stage={
          <>
            <StageHead {...stage} mode={mapMode} onMode={setMapMode} toneAvailable={toneAvailable} />
            <GlobeSlot>
              <GlobeThree
                countries={COUNTRIES}
                iso3={ISO3}
                tone={globeTone}
                minSample={MIN_SAMPLE}
                focus={spot ?? view.country}
                highlight={pick}
                pinCities={PIN_CITIES}
                pinsOf={pinsOfCountry}
                spinControl={false}
                onSelectCountry={pickCountry}
                onOpenCountry={(id) => go(toCountry(view, id))}
                onSelectPin={(p) => go(toCountry(view, p.cid))}
              />
              <ToneLegend
                topicName={globeTone?.name}
                minSample={MIN_SAMPLE}
                onClear={() => setMapMode('volume')}
              />
            </GlobeSlot>
            <StageFoot toneOn={toneOn} minSample={MIN_SAMPLE} />
          </>
        }
        panel={<Panel view={view} go={go} today={today} spot={spot} onSpot={spotCountry} />}
      />

      <CommandPalette
        open={paletteOpen}
        onClose={closePalette}
        quick={COUNTRIES.map((c) => ({ flag: c.flag, name: c.name, count: `${fmt(c.today)}건` }))}
        onSelect={(name) => go(toCountry(view, COUNTRIES.find((c) => c.name === name).id))}
      />
    </>
  );
}

/* ═══════════════ 오른쪽 패널 ═══════════════ */

/**
 * 패널 맨 위 이동 줄.
 * 뒤로가기는 좌표를 한 칸 올리고, 브레드크럼은 원하는 칸으로 한 번에 점프한다.
 * 뒤로가기 라벨은 "올라갈 좌표의 이름"이라 어디서 왔든 항상 맞다.
 */
function PanelNav({ view, go }) {
  if (!canGoBack(view)) return null;
  const parent = backOf(view);
  const crumbs = crumbsOf(view, go);
  return (
    <div className={s.panelNav}>
      <BackLink onClick={() => go(parent)}>← {josaRo(titleOf(parent))}</BackLink>
      {crumbs.length > 0 && <TaxonomyPath items={crumbs} />}
    </div>
  );
}

function Panel({ view, go, today, spot, onSpot }) {
  const level = levelOf(view);
  const body = (() => {
    switch (level) {
      case 'issue': return <IssueScreen view={view} go={go} spot={spot} onSpot={onSpot} />;
      case 'theme': return <ThemeScreen view={view} go={go} />;
      case 'field': return <FieldScreen view={view} go={go} />;
      case 'country': return <CountryScreen view={view} go={go} />;
      case 'themes': return <ThemesScreen view={view} go={go} />;
      case 'attention': return <AttentionScreen view={view} go={go} />;
      case 'articles': return <ArticlesScreen view={view} go={go} />;
      default: return <DashScreen view={view} go={go} today={today} />;
    }
  })();
  return (
    <>
      <PanelNav view={view} go={go} />
      {body}
    </>
  );
}

/* ── 글로벌 동향 ── */
function DashScreen({ view, go, today }) {
  const hot = ISSUES.slice().sort((a, b) => b.delta - a.delta).slice(0, 5);

  return (
    <>
      <PanelTopline label="글로벌 요약" />
      <PanelHeading title="글로벌 동향" desc="세계 뉴스의 변화를 한눈에 확인하세요." updated="방금 업데이트" />

      <KpiCards
        items={[
          { label: '전체 수집 기사', value: fmt(GRAND_TOTAL), unit: '건', trend: '+8.4%' },
          {
            label: (
              <>
                <LiveDot />
                오늘 수집 기사
              </>
            ),
            value: fmt(today),
            unit: '건',
            trend: '+12.1%',
          },
        ]}
      />

      <SectionTitle title="실시간 이슈 TOP 5" note="증가율 순 · 클릭하면 논조 분석" />
      <IssueCardList issues={hot.map(toIssueCard)} onSelect={(i) => go(toIssue(view, hot[i].id))} />

      {/* '분야로 좁혀 보기'와 '새롭게 떠오르는 테마'는 화면에서 뺐다.
          지우지 않고 components/panel/DashExplore.jsx로 옮겨 뒀다 — 다시 붙일 때는
          <FieldNarrow onSelect={...} /> · <RisingThemes onAll={...} /> 두 줄이면 된다. */}

      <PolicyNote>
        원문은 저장하지 않습니다 — <b>요약본 + 원문 링크</b>만 제공됩니다 · GDELT · NAVER News API · RSS
      </PolicyNote>
    </>
  );
}

/* ── 이슈 논조 ── */
function IssueScreen({ view, go, spot, onSpot }) {
  const iss = I(view.issueId);
  const theme = T(iss.theme);
  const arts = articlesOfTheme(iss.theme).slice(0, 4).map(toArticleCard);
  const reliable = Object.values(iss.tone).filter(hasSample).length;

  return (
    <>
      <PanelTopline label="이슈 논조 분석" />
      <IssueHero
        badge={`${theme.name} · 급상승 이슈`}
        title={iss.title}
        desc={iss.summary}
        stats={[
          { label: '분석 기사', value: `${fmt(iss.n)}건` },
          { label: '증가율', value: `+${iss.delta}%`, up: true },
          { label: '표본 충족', value: `${reliable}/${Object.keys(iss.tone).length}개국` },
        ]}
      />

      <SectionTitle title="국가별 논조" note="평균 대신 분포 · 누르면 지구본 이동" />
      {/* 나라를 누르면 화면을 옮기지 않는다 — 이슈를 계속 보면서 지구본만 그 나라로 돌린다.
          국가 분석으로 들어가는 길은 지구본 더블클릭과 필터 칩이 이미 맡고 있다(결정표 2-C). */}
      <ToneScatter issue={iss} spot={spot} onSelectCountry={onSpot} />

      <SectionTitle
        title="이 테마의 대표 기사"
        action={{ label: '전체 보기 →', onClick: () => go(openAside(view, 'articles', { tone: 'all' })) }}
      />
      <ArticleFeed articles={arts} />

      <PolicyNote>논조 점수만 자체 산출이며, 매체 성향 라벨은 외부 평가기관 값입니다.</PolicyNote>
    </>
  );
}

/* ── 테마 상세 ── */
function ThemeScreen({ view, go }) {
  const t = T(view.themeId);
  const issues = issuesOfTheme(view.themeId);
  const arts = articlesOfTheme(view.themeId).slice(0, 3).map(toArticleCard);

  return (
    <>
      <PanelTopline label="테마 상세" />
      <SubHeading title={t.name} desc={`${t.issueCount}개 이슈, 표본 ${fmt(t.n)}건을 분석했습니다.`} />

      <SummaryBox
        items={[
          { label: '최근 24시간', value: t.rise, note: '직전 기간 대비 기사량' },
          { label: '분석 표본', value: `${fmt(t.n)}건`, note: `${COUNTRIES.length}개국 합계` },
          { label: '주요 이슈', value: `${t.issueCount}개`, note: '현재 급상승 이슈' },
        ]}
      />

      <SectionTitle title={`${t.name} 테마의 주요 이슈`} note="이슈 선택 후 논조 확인" />
      <ThemeIssueList issues={issues.map(toThemeIssue)} onSelect={(i) => go(toIssue(view, issues[i].id))} />

      <SectionTitle
        title="이 테마의 대표 기사"
        action={{ label: '기사 전체 보기 →', onClick: () => go(openAside(view, 'articles', { tone: 'all' })) }}
      />
      <ArticlePreviewList articles={arts} />
    </>
  );
}

/* ── 분야 ──
   결정표 1-3의 3단(분야 → 테마 → 이슈)에서 그동안 비어 있던 칸이다.
   브레드크럼에만 나오고 갈 데가 없으면 계층을 선언만 하고 지키지 않는 셈이라 화면을 만들었다. */
function FieldScreen({ view, go }) {
  const f = FIELD(view.fieldId);
  const themes = themesOfField(view.fieldId);
  const issues = issuesOfField(view.fieldId).slice().sort((a, b) => b.delta - a.delta);
  const sample = themes.reduce((sum, t) => sum + t.n, 0);

  return (
    <>
      <PanelTopline label="분야" />
      <SubHeading
        title={f.name}
        desc={`테마 ${themes.length}개 · 이슈 ${issues.length}개 · 표본 ${fmt(sample)}건`}
      />

      <SectionTitle title={`${f.name} 분야의 테마`} note="표본 순" />
      <ThemeDetailList
        themes={themes
          .slice()
          .sort((a, b) => b.n - a.n)
          .map(toThemeCard)}
        onSelect={(i) =>
          go(toTheme(view, themes.slice().sort((a, b) => b.n - a.n)[i].id))
        }
      />

      <div style={{ marginTop: 24 }}>
        <SectionTitle title={`${f.name} 분야의 이슈`} note="증가율 순" />
        <IssueCardList
          issues={issues.map(toIssueCard)}
          onSelect={(i) => go(toIssue(view, issues[i].id))}
        />
      </div>
    </>
  );
}

/* ── 국가 분석 ── */
function CountryScreen({ view, go }) {
  const id = view.country;
  const c = C(id);
  const tone = countryToneOf(id);
  const themes = countryThemeRows(id, 3);
  const arts = ARTICLES.filter((a) => a.country === id).slice(0, 2).map(toArticleCard);
  const rank = COUNTRIES.slice().sort((a, b) => b.today - a.today).findIndex((x) => x.id === id) + 1;

  return (
    <>
      <PanelTopline label="국가 분석" />
      <CountryIdentity flag={c.flag} name={c.name} meta={`${c.src} · 매체 ${c.m}곳`} />

      <KpiCards
        items={[
          { label: '오늘 수집 기사', value: fmt(c.today), unit: '건', trend: '+14.2%' },
          { label: '기사량 순위', value: String(rank), unit: `위 / ${COUNTRIES.length}`, trend: '↑ 2' },
        ]}
      />

      <div className="wtw-tone-note">
        <b>
          {c.name}의 전반 논조는 {toneLabel3(tone.s)}입니다.
        </b>{' '}
        표본 {fmt(tone.n)}건 기준이며, 이 값은 패널 배경색으로만 씁니다. 개별 이슈에서는 평균 대신
        나라별 분포를 봅니다.
      </div>

      <Divider>주요 데이터</Divider>

      <SectionTitle
        title="급상승 테마"
        action={{ label: '전체 보기 →', onClick: () => go(openAside(view, 'themes')) }}
      />
      <ThemeCardList themes={themes} onSelect={(i) => go(toTheme(view, themes[i].themeId))} />

      <div style={{ marginTop: 24 }}>
        <SectionTitle
          title={`${c.name}이 많이 언급한 국가`}
          action={{
            label: '전체 보기 →',
            onClick: () => go(openAside(view, 'attention', { direction: 'outgoing' })),
          }}
        />
        <AttentionList rows={attentionRows(id, 'outgoing')} />
      </div>

      <div style={{ marginTop: 22 }}>
        <SectionTitle
          title="대표 기사"
          action={{ label: '전체 보기 →', onClick: () => go(openAside(view, 'articles', { tone: 'all' })) }}
        />
        <ArticlePreviewList articles={arts} />
      </div>

      <PolicyNote>
        본문 미저장 원칙 — 요약은 <b>KoBART / BART-large-CNN</b>으로 생성되었습니다.
      </PolicyNote>
    </>
  );
}

/* ── 곁가지: 테마 전체 ──
   분야별로 묶어서 보여준다. 평평하게 늘어놓으면 분야가 또 라벨로만 남는다. */
function ThemesScreen({ view, go }) {
  return (
    <>
      <PanelTopline label="테마 분석" />
      <SubHeading
        title="분야별 테마"
        desc="분야 아래 테마를 모두 펼쳤습니다. 분야 이름을 누르면 그 분야만 봅니다."
      />

      {FIELDS.map((f) => {
        const themes = themesOfField(f.id).slice().sort((a, b) => b.delta - a.delta);
        if (!themes.length) return null;
        return (
          <div key={f.id} style={{ marginBottom: 22 }}>
            <SectionTitle
              title={f.name}
              action={{ label: '이 분야만 보기 →', onClick: () => go(toField(view, f.id)) }}
            />
            <ThemeDetailList
              themes={themes.map(toThemeCard)}
              onSelect={(i) => go(toTheme(view, themes[i].id))}
            />
          </div>
        );
      })}
    </>
  );
}

/* ── 곁가지: 국가 관심도 ── */
function AttentionScreen({ view, go }) {
  const id = view.country; /* 국가 분석에서만 열리는 곁가지다 */
  const lead = attentionLead(id, view.direction);
  return (
    <>
      <PanelTopline label="국가 관심도" />
      <SubHeading
        title="국가 관심도"
        desc={`겹치는 보도 주제로 잰 값입니다. ${lead.top.name}이 ${lead.share}%로 가장 큽니다.`}
      />
      <AttentionPanel
        country={C_NAME(id)}
        direction={view.direction}
        onDirection={(d) => go({ ...view, direction: d })}
        rows={attentionRows(id, view.direction)}
      />
    </>
  );
}

/* ── 곁가지: 테마별 기사 ── */
function ArticlesScreen({ view, go }) {
  const quick = THEMES.slice().sort((a, b) => b.delta - a.delta).slice(0, 5);

  /* 좌표가 곧 필터다 — 테마 칸이 차 있으면 그 테마의 기사만 */
  const pool = view.themeId ? articlesOfTheme(view.themeId) : ARTICLES;
  const cards = pool.map(toArticleCard);
  const filtered = view.tone === 'all' ? cards : cards.filter((a) => a.tone === view.tone);

  const quickIndex = view.themeId ? quick.findIndex((t) => t.id === view.themeId) : -1;

  return (
    <>
      <PanelTopline label="테마별 기사" />
      <SubHeading title="대표 기사" desc="먼저 테마를 선택하고 관련 기사를 확인하세요." />

      <ThemeFilterPanel
        quickThemes={quick.map(toThemeCard)}
        catalog={CATALOG}
        fields={FIELDS.map((f) => f.name)}
        selectedIndex={quickIndex >= 0 ? quickIndex : null}
        selectedTheme={view.themeId ? toThemeCard(T(view.themeId)) : null}
        totalLabel={String(THEMES.length)}
        onSelectQuick={(i) =>
          go({ ...view, themeId: i === null ? null : quick[i].id, issueId: null, tone: 'all' })
        }
        onSelectCatalog={(i) => go({ ...view, themeId: themeIdFromCatalog(i), issueId: null, tone: 'all' })}
      />

      <ArticleFilterBar tone={view.tone} onTone={(t) => go({ ...view, tone: t })} />

      <ResultHead
        title={`${view.themeId ? T_NAME(view.themeId) : '전체 테마'} 기사`}
        count={`${filtered.length}개 대표 기사`}
      />
      <ArticleFeed articles={filtered} />
    </>
  );
}
