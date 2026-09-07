import s from './panel.module.css';

/**
 * 이슈 히어로 — 뱃지 · 제목 · 요약 · 지표 3개.
 * 출처: 아카이브/app.js .issue-hero
 *
 * @param {{badge: string, title: string, desc: string,
 *          stats: {label: string, value: string, up?: boolean}[]}} props
 */
export default function IssueHero({ badge, title, desc, stats }) {
  return (
    <div className={s.hero}>
      <span className={s.badge}>{badge}</span>
      <h2>{title}</h2>
      <p>{desc}</p>
      <div className={s.heroStats}>
        {stats.map((st) => (
          <span key={st.label}>
            {st.label}
            <b className={st.up ? s.up : ''}>{st.value}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/** 테마 요약 3칸 */
export function SummaryBox({ items }) {
  return (
    <div className={s.summaryBox}>
      {items.map((it) => (
        <div key={it.label}>
          <span>{it.label}</span>
          <strong>{it.value}</strong>
          <small>{it.note}</small>
        </div>
      ))}
    </div>
  );
}
