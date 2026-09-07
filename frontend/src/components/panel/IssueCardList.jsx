import s from './panel.module.css';

/**
 * 글로벌 이슈 TOP 5 카드 — 분야·테마 꼬리표, 기사량, 관련 국기, 증가율 스파크라인.
 * 출처: 아카이브/app.js renderGlobal() .issue-card
 *
 * @param {{issues: {field: string, theme: string, title: string, count: string,
 *                   change: string, countries: string, path: string}[],
 *          onSelect?: (index: number) => void}} props
 */
export default function IssueCardList({ issues, onSelect }) {
  return (
    <div className={s.issueList}>
      {issues.map((issue, index) => (
        <button
          key={issue.title}
          type="button"
          className={s.issueCard}
          onClick={() => onSelect?.(index)}
        >
          <span className={s.issueRank}>{String(index + 1).padStart(2, '0')}</span>
          <span className={s.issueMain}>
            <span className={s.taxonomyMini}>
              {issue.field} · {issue.theme}
            </span>
            <strong>{issue.title}</strong>
            <span className={s.issueMeta}>
              <span>{issue.count}</span>
              <span className={s.mini}>{issue.countries}</span>
            </span>
          </span>
          <span className={s.issueSide}>
            <strong>{issue.change}</strong>
            <Sparkline path={issue.path} />
          </span>
        </button>
      ))}
    </div>
  );
}

/** 46×14 미니 추세선 */
export function Sparkline({ path }) {
  return (
    <svg className={s.sparkline} viewBox="0 0 46 14" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}
