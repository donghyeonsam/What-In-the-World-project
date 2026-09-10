import s from './layout.module.css';

/**
 * 대시보드 골격 — 지도 스테이지 + 인사이트 패널. 둘 다 흰 바탕이다.
 * 결정표 2-2(패널이 각자 스크롤) · 3-1(라이트 미니멀) · 4(3D 지구본) · 7-3(데스크톱 전용)
 *
 * panelTone은 "지금 보고 있는 나라가 이 이슈를 어떻게 썼는가"를 배경 그라데이션으로 말한다.
 * pos = 우호(초록), neg = 비판(빨강), neu = 중립(회색).
 *
 * @param {{header: React.ReactNode, stage: React.ReactNode,
 *          panel: React.ReactNode, panelTone?: 'pos'|'neg'|'neu'|null,
 *          panelRef?: React.Ref<HTMLElement>}} props
 */
export default function DashboardLayout({ header, stage, panel, panelTone = null, panelRef }) {
  const toneClass = panelTone
    ? { pos: s.tonePos, neg: s.toneNeg, neu: s.toneNeu }[panelTone]
    : '';
  return (
    <div className={s.shell}>
      {header}
      <main className={s.dashboard}>
        <section className={s.stage} aria-label="글로벌 지도">
          {stage}
        </section>
        <aside className={`${s.panel} ${toneClass}`} aria-live="polite" ref={panelRef}>
          {panel}
        </aside>
      </main>
    </div>
  );
}

/** 지구본이 들어갈 자리 */
export function GlobeSlot({ children }) {
  return <div className={s.globeSlot}>{children}</div>;
}
