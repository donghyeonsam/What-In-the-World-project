/* ─────────────────────────────────────────────────────────────
   어댑터

   컴포넌트들은 원래 서로 다른 시안에서 왔고, 각자 자기 모양의 데이터를 먹는다.
   모델을 그 모양으로 바꿔주는 자리를 여기 한 곳에 모았다.
   컴포넌트를 고치는 대신 어댑터를 두면, 나중에 실제 API가 붙어도
   손댈 곳이 이 파일 하나로 끝난다.
   ───────────────────────────────────────────────────────────── */

import { toneVar, toneLabel3 } from '../lib/tone.js';
import {
  C, C_NAME, T, T_NAME, FIELD_NAME, ISSUES, THEMES, ARTICLES,
  themeSampleOf, hasSample, issuesOfTheme,
} from './model.js';

const fmt = (n) => n.toLocaleString('ko-KR');

/* ── 이슈 → IssueCardList (미니멀) ──
   {field, theme, title, count, change, countries, path} */
export function toIssueCard(issue) {
  const flags = Object.entries(issue.tone)
    .filter(([, d]) => hasSample(d))
    .sort((a, b) => b[1].n - a[1].n)
    .slice(0, 3)
    .map(([cid]) => C(cid).flag)
    .join(' ');
  return {
    field: FIELD_NAME(T(issue.theme).field),
    theme: T_NAME(issue.theme),
    title: issue.title,
    count: `${fmt(issue.n)}건`,
    change: `+${issue.delta}%`,
    countries: flags,
    path: issue.spark,
  };
}

/* ── 테마 → ThemeCardList / ThemeDetailList (미니멀) ──
   {name, field, count, rise, leadingIssue, bars} */
export function toThemeCard(theme) {
  return {
    name: theme.name,
    field: FIELD_NAME(theme.field),
    count: `${fmt(theme.n)}건`,
    rise: theme.rise,
    leadingIssue: theme.leadingIssue,
    bars: theme.bars,
  };
}

/* ── 테마 안의 이슈 → ThemeIssueList (미니멀) ── */
export function toThemeIssue(issue) {
  return { title: issue.title, count: `${fmt(issue.n)}건`, rise: `+${issue.delta}%` };
}

/* ── 기사 → ArticleFeed / ArticlePreviewList (미니멀) ──
   모델은 논조를 스칼라 s로 들고 있고, 컴포넌트는 'positive|neutral|negative'를 먹는다.
   여기서 한 번만 변환한다. 되돌릴 일이 없으므로 손실이 문제되지 않는다. */
export function toArticleCard(a) {
  const tone = a.s > 0.18 ? 'positive' : a.s < -0.18 ? 'negative' : 'neutral';
  return {
    id: a.id,
    tone,
    toneLabel: toneLabel3(a.s),
    source: a.source,
    time: `${a.minutes}분 전`,
    title: a.title,
    summary: a.summary,
    /* 아래는 미니멀 컴포넌트가 안 쓰지만 화면에서 쓸 수 있게 남긴다 */
    s: a.s,
    country: a.country,
    theme: a.theme,
    cross: a.cross,
    color: toneVar(a.s),
  };
}

/* ── 테마 목록 → ThemeFilterPanel (미니멀) ── */
export function themeCatalog() {
  return THEMES.slice()
    .sort((a, b) => b.delta - a.delta)
    .map(toThemeCard);
}

/** ThemeFilterPanel이 고른 카탈로그 인덱스를 테마 id로 되돌린다 */
export function themeIdFromCatalog(index) {
  return THEMES.slice().sort((a, b) => b.delta - a.delta)[index]?.id ?? null;
}

/* ── 국가 → 지구본 핀 ──
   GlobeThree는 국가 포커스 시 arts를 핀으로 펼친다. tr은 신뢰도(핀 색). */
export function pinsOfCountry(country) {
  return ARTICLES.filter((a) => a.country === country.id)
    .slice(0, 5)
    .map((a) => ({ title: a.title, tr: a.trust }));
}

/* ── 국가별 요약 문구 ── */
export function countrySummary(cid) {
  const c = C(cid);
  const covered = ISSUES.filter((i) => i.tone[cid]).length;
  const reliable = ISSUES.filter((i) => hasSample(i.tone[cid])).length;
  return `매체 ${c.m}곳 · 다룬 이슈 ${covered}건 중 ${reliable}건이 표본 충족`;
}

/** 테마별로 그 국가가 낸 표본 수 (급상승 테마 정렬용) */
export function countryThemeRows(cid, limit = 5) {
  return THEMES.map((t) => ({ t, n: themeSampleOf(cid, t.id) }))
    .filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n)
    .slice(0, limit)
    .map(({ t, n }) => ({
      ...toThemeCard(t),
      count: `${fmt(n)}건`,
      leadingIssue: issuesOfTheme(t.id).slice().sort((a, b) => (b.tone[cid]?.n ?? 0) - (a.tone[cid]?.n ?? 0))[0]?.title ?? '',
      themeId: t.id,
    }));
}

export { C_NAME, fmt };
