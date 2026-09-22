import s from './panel.module.css';
import FieldBadge from './FieldBadge.jsx';

/**
 * 이슈 순위 카드 — 등수, 분야 배지, 제목. 테마는 배지 툴팁으로 표시한다.
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
          <span className={s.issueField}><FieldBadge field={issue.field} theme={issue.theme} /></span>
          <span className={s.issueMain}>
            <strong>{issue.title}</strong>
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
