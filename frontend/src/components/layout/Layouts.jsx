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

/**
 * 스테이지 머리말 + 지도 표시 기준 스위치.
 *
 * 결정표 6번 "논조 모드 잠금": 논조를 볼 맥락(선택된 이슈)이 없으면
 * 스위치를 라벨로 낮춰서, 누를 수 있을 것 같은 기대를 애초에 만들지 않는다.
 *
 * @param {{eyebrow: string, title: React.ReactNode, desc: string,
 *          mode?: 'volume'|'tone', onMode?: (m: string) => void,
 *          toneAvailable?: boolean}} props
 */
export function StageHead({ eyebrow, title, desc, mode = 'volume', onMode, toneAvailable = false }) {
  return (
    <div className={s.stageHead}>
      <div>
        <div className={s.eyebrow}>{eyebrow}</div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
      <div className={`${s.switch} ${toneAvailable ? '' : s.locked}`} role="group" aria-label="지도 표시 기준">
        <button
          type="button"
          className={mode === 'volume' ? s.on : ''}
          onClick={() => toneAvailable && onMode?.('volume')}
        >
          {toneAvailable ? '수집 현황' : '지도 기준 · 수집 현황'}
        </button>
        {toneAvailable && (
          <button
            type="button"
            className={mode === 'tone' ? s.on : ''}
            onClick={() => onMode?.('tone')}
          >
            여론 톤
          </button>
        )}
      </div>
    </div>
  );
}

/** 지구본이 들어갈 자리 */
export function GlobeSlot({ children }) {
  return <div className={s.globeSlot}>{children}</div>;
}

/**
 * 스테이지 바닥 — 톤 색 축과 표본 부족 표시를 같이 둔다.
 * 색만 칠하고 축을 안 주면 무슨 색이 무슨 뜻인지 알 수 없다.
 */
export function StageFoot({ toneOn, minSample, updated = '10분 전 갱신', right }) {
  return (
    <div className={s.stageFoot}>
      {toneOn ? (
        <>
          <span className={s.ramp}>
            비판 <i /> 우호
          </span>
          <span className={s.lowSample}>
            <i />
            표본 부족 · 기사 {minSample}건 미만
          </span>
        </>
      ) : (
        <span>지구본의 빛나는 지점이 수집 대상 국가입니다 · 클릭 = 목록 좁히기 · 더블클릭 = 국가 분석</span>
      )}
      <span className={s.spacer} />
      <span>{updated}</span>
      {right}
    </div>
  );
}
