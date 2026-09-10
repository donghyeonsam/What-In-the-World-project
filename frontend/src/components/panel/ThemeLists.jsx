import s from './panel.module.css';

/**
 * 급상승 테마 요약 목록 — 순위 · 분야 · 이름 · 대표 이슈 · 증가율.
 * 출처: 아카이브/app.js countryOverviewMarkup() .theme-card
 *
 * @param {{themes: object[], limit?: number, onSelect?: (index: number) => void}} props
 */
export function ThemeCardList({ themes, limit, onSelect }) {
  const list = limit ? themes.slice(0, limit) : themes;
  return (
    <div className={s.themeList}>
      {list.map((theme, index) => (
        <button
          key={theme.name}
          type="button"
          className={s.themeCard}
          onClick={() => onSelect?.(index)}
        >
          <span className={s.rank}>{String(index + 1).padStart(2, '0')}</span>
          <span className={s.themeCardMain}>
            <span className={s.themeCardTitle}>
              <strong>{theme.name}</strong>
              <small className={s.themeField}>{theme.field}</small>
            </span>
            {theme.leadingIssue && <small className={s.themeCardIssue}>주요 이슈 · {theme.leadingIssue}</small>}
          </span>
          <span className={s.themeCardMetric}>
            <strong>{theme.count}</strong>
            <small>최근 24시간</small>
            {theme.rise && <b>{theme.rise}</b>}
          </span>
        </button>
      ))}
    </div>
  );
}

/**
 * 테마 분석 목록 — 최근 7일 기사량 막대를 함께 그려 "얼마나 가파른가"를 보여준다.
 * 출처: 아카이브/app.js countryThemeListMarkup()
 *
 * @param {{themes: object[], intro?: {label: string, title: string, note: string},
 *          onSelect?: (index: number) => void}} props
 */
export function ThemeDetailList({ themes, intro, onSelect }) {
  return (
    <>
      {intro && (
        <div className={s.analysisIntro}>
          <div>
            <span>{intro.label}</span>
            <strong>{intro.title}</strong>
          </div>
          <p>{intro.note}</p>
        </div>
      )}
      <div className={s.themeAnalysisList}>
        {themes.map((theme, index) => (
          <button
            key={theme.name}
            type="button"
            className={s.themeDetailCard}
            onClick={() => onSelect?.(index)}
          >
            <span className={s.themeDetailRank}>{String(index + 1).padStart(2, '0')}</span>
            <span className={s.themeDetailBody}>
              <span className={s.themeDetailHead}>
                <strong>{theme.name}</strong>
                <b>{theme.rise}</b>
              </span>
              <span className={s.themeDetailMeta}>
                {theme.field} · 최근 24시간 기사 {theme.count}
              </span>
              {theme.bars?.length > 0 && <span className={s.volumeBars} aria-label="최근 24개 시간 구간 기사량">
                {theme.bars?.map((h, i) => (
                  // eslint-disable-next-line react/no-array-index-key
                  <i key={i} style={{ height: `${h}%` }} title={theme.timestamps?.[i] ? `${theme.timestamps[i].time} · ${theme.timestamps[i].articleCount}건` : undefined} />
                ))}
              </span>}
              {theme.leadingIssue && <span className={s.leading}>주요 이슈 · {theme.leadingIssue}</span>}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

/**
 * 테마 요약 3칸 — 증가율 / 기사 수 / 이슈 수.
 * 출처: 아카이브/app.js .theme-summary-box
 */
export function ThemeSummaryBox({ items }) {
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

/**
 * 테마 안의 이슈 목록.
 * 출처: 아카이브/app.js .theme-issue-list
 */
export function ThemeIssueList({ issues, onSelect }) {
  return (
    <div className={s.themeIssueList}>
      {issues.map((issue, i) => (
        <button key={issue.title} type="button" onClick={() => onSelect?.(i)}>
          <span className={s.issueType}>이슈 {String(i + 1).padStart(2, '0')}</span>
          <span>
            <strong>{issue.title}</strong>
            {issue.count != null && <small>기사 {issue.count}</small>}
          </span>
          <b>{issue.rise}</b>
          <i>›</i>
        </button>
      ))}
    </div>
  );
}
