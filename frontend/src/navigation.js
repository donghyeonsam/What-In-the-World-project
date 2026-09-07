/* ─────────────────────────────────────────────────────────────
   화면 좌표

   예전에는 화면을 이름(`{name:'issue', id}`)으로 들고 다녔다.
   그러면 뒤로가기 목적지를 "지금 무슨 화면인가"로 추론하게 되는데,
   이 앱의 이동 그래프는 트리가 아니라 그래프다 —
   이슈로 들어오는 길이 대시보드·테마 상세·기사 목록 셋이다.
   부모를 하나로 가정하니 "국가 → 테마 → 이슈 → 뒤로 = 대시보드"처럼
   두 계단을 건너뛰고, 국가 필터까지 잃었다.

   그래서 화면을 이름 대신 좌표로 표현한다.

   축이 둘이다. 섞으면 안 된다.

     [분류 축]  전체 ─ 분야 ─ 테마 ─ 이슈     ← 깊이가 있다. 브레드크럼은 이 축만 그린다.
     [국가 축]  전체 │ 특정 국가              ← 깊이가 아니라 on/off. 필터 칩이 맡는다.

     scope    국가 필터 — 직교축이다. 계층 이동으로는 풀리지 않는다.
     country  국가 개요로 들어갔는가 (지구본 더블클릭)
     fieldId  분류 1단
     themeId  분류 2단
     issueId  분류 3단
     aside    계층 밖 곁가지. 열었던 자리로 그대로 되돌아온다.

   scope와 country를 나눠 둔 이유는 결정표 2-C 때문이다.
   한 번 클릭은 "목록만 좁히기"(scope)라 화면을 옮기지 않고,
   더블클릭은 "국가 개요로 들어가기"(country)라 화면을 옮긴다.
   들어간 상태에서 뒤로 가면 country만 풀리고 scope는 남는다 —
   보던 나라를 계속 보고 있다는 사실은 유지되어야 하기 때문이다.
   ───────────────────────────────────────────────────────────── */

import { I, T, C_NAME, T_NAME, FIELD_NAME } from './data/model.js';

export const HOME = {
  scope: null,
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
  if (v.country) return { ...v, country: null }; /* 국가 필터(scope)는 남긴다 */
  return { ...v, scope: null };
}

/** 이 화면 위에 올라갈 화면이 있는가.
    대시보드에서는 없다 — 국가 필터만 남은 상태는 화면 이동이 아니라 필터라서,
    해제는 뒤로가기가 아니라 필터 칩의 '해제 ×'가 맡는다. */
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

/** 국가 개요로 들어가기 — 필터도 같이 걸린다 */
export const toCountry = (v, id) => ({
  ...v,
  scope: id,
  country: id,
  fieldId: null,
  themeId: null,
  issueId: null,
  aside: null,
});

/** 지구본 한 번 클릭 — 목록만 좁힌다. 같은 나라를 다시 누르면 해제. */
export const toggleScope = (v, id) =>
  v.scope === id ? { ...v, scope: null, country: null } : { ...v, scope: id };

export const toDash = (v) => ({ ...HOME, scope: v.scope });

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

  const items = [{ label: '전체', value: '모든 분야', onClick: () => go(toDash(v)) }];

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
