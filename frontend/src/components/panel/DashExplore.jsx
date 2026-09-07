import { FIELDS, THEMES, themesOfField, issuesOfField } from '../../data/model.js';
import { SectionTitle, FieldChips, TrendTags } from './PanelChrome.jsx';

/* ─────────────────────────────────────────────────────────────
   글로벌 동향의 탐색 블록 — 지금은 화면에 붙이지 않는다.

   원래 대시보드 아래쪽에 이슈 TOP 5 다음으로 두 블록이 붙어 있었다.
   빼기로 했으므로 App에서는 렌더하지 않지만, 지우지 않고 여기로 옮겨 둔다.
   다시 붙일 때는 App의 DashScreen에서 이렇게 부르면 된다.

     <FieldNarrow onSelect={(id) => go(toField(view, id))} />
     <RisingThemes onAll={() => go(openAside(view, 'themes'))} />

   데이터는 컴포넌트가 직접 모델에서 읽는다. 부르는 쪽은 '눌렀을 때 어디로 갈지'만 정한다 —
   그래야 붙이고 떼는 일이 한 줄로 끝난다.
   ───────────────────────────────────────────────────────────── */

/** 분야로 좁혀 보기 — 분야 → 테마 → 이슈 계층의 첫 칸으로 들어가는 입구 */
export function FieldNarrow({ onSelect }) {
  return (
    <div style={{ marginTop: 24 }}>
      <SectionTitle title="분야로 좁혀 보기" note="분야 → 테마 → 이슈" />
      <FieldChips
        fields={FIELDS.map((f) => ({
          ...f,
          themeCount: themesOfField(f.id).length,
          issueCount: issuesOfField(f.id).length,
        }))}
        onSelect={onSelect}
      />
    </div>
  );
}

/** 새롭게 떠오르는 테마 — 증가율 상위 3개. '전체 보기'는 테마 곁가지를 연다. */
export function RisingThemes({ onAll, count = 3 }) {
  const rising = THEMES.slice()
    .sort((a, b) => b.delta - a.delta)
    .slice(0, count);

  return (
    <div style={{ marginTop: 24 }}>
      <SectionTitle
        title="새롭게 떠오르는 테마"
        action={onAll ? { label: '전체 보기 →', onClick: onAll } : undefined}
      />
      <TrendTags tags={rising.map((t) => ({ label: t.name, value: t.rise }))} />
    </div>
  );
}
