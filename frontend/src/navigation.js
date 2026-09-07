/* ─────────────────────────────────────────────────────────────
   화면 좌표

   예전에는 화면을 이름(`{name:'issue', id}`)으로 들고 다녔다.
   그러면 뒤로가기 목적지를 "지금 무슨 화면인가"로 추론하게 되는데,
   이 앱의 이동 그래프는 트리가 아니라 그래프다 —
   이슈로 들어오는 길이 대시보드·테마 상세·기사 목록 셋이다.
   부모를 하나로 가정하니 "국가 → 테마 → 이슈 → 뒤로 = 대시보드"처럼
   두 계단을 건너뛰고, 국가 필터까지 잃었다.

   그래서 화면을 이름 대신 좌표로 표현한다.

   축은 하나다.

     [분류 축]  전체 ─ 분야 ─ 테마 ─ 이슈     ← 깊이가 있다. 브레드크럼이 이 축을 그린다.

     country  국가 분석으로 들어갔는가 (지구본 더블클릭)
     fieldId  분류 1단
     themeId  분류 2단
     issueId  분류 3단
     aside    계층 밖 곁가지. 열었던 자리로 그대로 되돌아온다.

   예전에는 국가 축(scope)이 하나 더 있었다. 지구본을 한 번 누르면 목록이 그 나라로 좁혀지고,
   그 필터는 계층 이동으로 풀리지 않았다(결정표 2-C). 그걸 뺐다. 이유는 둘이다.

     · 국가 분석에 들어갔다 뒤로 나오면 필터만 남아, 글로벌 동향이
       "한국이 다룬 이슈 TOP 5"가 됐다. 세계 전체를 보는 화면에 한 나라 목록이 놓인 셈이다.
     · 같은 목록이 어떤 때는 전체, 어떤 때는 한 나라 기준이라, 지금 무엇을 보는지 읽기 어려웠다.

   국가에 대한 정보는 국가 분석 화면 하나가 맡는다.
   지구본 한 번 클릭은 화면을 두고 지구본만 표시한다(App의 pick) — 좌표를 건드리지 않는다.
   ───────────────────────────────────────────────────────────── */

import { I, T, C_NAME, T_NAME, FIELD_NAME } from './data/model.js';

export const HOME = {
  country: null,
  fieldId: null,
  themeId: null,
  issueId: null,
  aside: null,
  direction: 'outgoing', /* 관심도 곁가지 */
  tone: 'all', /* 기사 곁가지 */
};

/** 좌표에서 지금 화면을 읽어낸다. 안쪽 칸이 이길수록 깊은 화면이다. */
export function levelOf(v) {
  if (v.aside) return v.aside; /* 'themes' | 'attention' | 'articles' */
  if (v.issueId) return 'issue';
  if (v.themeId) return 'theme';
  if (v.fieldId) return 'field';
  if (v.country) return 'country';
  return 'dash';
}

/** 그 좌표를 한 줄로 부르는 이름 — 뒤로가기 라벨과 브레드크럼에 쓴다 */
export function titleOf(v) {
  switch (levelOf(v)) {
    case 'themes': return '급상승 테마 전체';
    case 'attention': return '국가 관심도';
    case 'articles': return '테마별 기사';
    case 'issue': return '이슈 논조';
    case 'theme': return `${T_NAME(v.themeId)} 테마`;
    case 'field': return `${FIELD_NAME(v.fieldId)} 분야`;
    case 'country': return `${C_NAME(v.country)} 분석`;
    default: return '글로벌 동향';
  }
}

/**
 * 뒤로가기 = 가장 안쪽 칸 하나를 비우기.
 *
 * 이 사다리 덕분에 "국가 → 이슈 → 테마 → 국가"처럼 빙 돌아도 깊이가 얕아지지 않는다.
 * 어디서 왔든 좌표가 같으면 올라가는 곳도 같다.
 */
export function backOf(v) {
  if (v.aside) return { ...v, aside: null };
  if (v.issueId) return { ...v, issueId: null }; /* themeId는 toIssue가 이미 채워 뒀다 */
  if (v.themeId) return { ...v, themeId: null }; /* fieldId는 toTheme이 이미 채워 뒀다 */
  if (v.fieldId) return { ...v, fieldId: null };
  if (v.country) return { ...v, country: null };
  return v; /* 대시보드 — 올라갈 곳이 없다. canGoBack이 여기까지 오지 못하게 막는다. */
}

/** 이 화면 위에 올라갈 화면이 있는가. 대시보드가 바닥이다. */
export const canGoBack = (v) => levelOf(v) !== 'dash';

/* ── 이동 ──
   전부 좌표를 바꾸는 순수 함수다. "어디서 왔는지"를 기록하지 않는다. */

/* 아래 세 함수의 공통 규칙: 내려갈 때 자기 위 칸을 전부 채운다.
   어느 길로 들어왔든 좌표가 같아지므로, 올라가는 곳도 항상 같다.
   대시보드에서 이슈로 바로 뛰어도 분야·테마가 채워져 뒤로가기가 계단을 밟는다. */

export const toField = (v, fieldId) => ({ ...v, fieldId, themeId: null, issueId: null, aside: null });

export const toTheme = (v, themeId) => ({
  ...v,
  themeId,
  fieldId: T(themeId)?.field ?? v.fieldId,
  issueId: null,
  aside: null,
});

export const toIssue = (v, issueId) => {
  const themeId = I(issueId)?.theme ?? v.themeId;
  return { ...v, issueId, themeId, fieldId: T(themeId)?.field ?? v.fieldId, aside: null };
};

/** 국가 분석으로 들어가기. 국가 정보는 이 화면 안에서만 산다 — 나올 때 아무것도 남기지 않는다. */
export const toCountry = (v, id) => ({
  ...v,
  country: id,
  fieldId: null,
  themeId: null,
  issueId: null,
  aside: null,
});

export const toDash = () => HOME;

/** 곁가지 열기 — 닫으면 열었던 자리로 그대로 돌아온다 */
export const openAside = (v, aside, extra = {}) => ({ ...v, aside, ...extra });

/**
 * 브레드크럼 — 분류 축(전체 › 분야 › 테마 › 이슈)만 그린다.
 *
 * 국가는 일부러 뺐다. 국가는 계층이 아니라 필터라서, 여기 끼워 넣으면
 * 분야·테마·이슈가 국가 밑에 매달린 것처럼 읽힌다. 국가는 필터 칩이 따로 맡는다.
 *
 * 지금 있는 칸도 값을 보여주되 링크로 만들지 않는다 — 라벨만 덩그러니 남으면 깨져 보인다.
 */
export function crumbsOf(v, go) {
  const at = levelOf(v);
  if (at === 'dash' || at === 'country') return [];

  const items = [{ label: '전체', value: '모든 분야', onClick: () => go(toDash()) }];

  if (v.fieldId) {
    items.push({
      label: '분야',
      value: FIELD_NAME(v.fieldId),
      onClick: at === 'field' ? undefined : () => go(toField(v, v.fieldId)),
    });
  }
  if (v.themeId) {
    items.push({
      label: '테마',
      value: T_NAME(v.themeId),
      onClick: at === 'theme' ? undefined : () => go(toTheme(v, v.themeId)),
    });
  }
  if (v.issueId) {
    items.push({
      label: '이슈',
      value: I(v.issueId).title,
      onClick: at === 'issue' ? undefined : () => go(toIssue(v, v.issueId)),
    });
  }
  if (v.aside) items.push({ label: '지금', value: titleOf(v) });

  return items;
}
