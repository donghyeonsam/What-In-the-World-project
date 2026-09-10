import s from './panel.module.css';

const TONE_COLOR = {
  positive: 'var(--wtw-pos)',
  neutral: 'var(--wtw-neu)',
  negative: 'var(--wtw-neg)',
};

/**
 * 기사 미리보기 — 제목 한 줄과 논조 점 + 출처 + 시각.
 * 출처: 아카이브/app.js articlePreviewMarkup()
 */
export function ArticlePreviewList({ articles, limit }) {
  const list = limit ? articles.slice(0, limit) : articles;
  return (
    <>
      {list.map((a) => (
        <article className={s.articleCard} key={a.id ?? a.title}>
          <strong>{a.url ? <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a> : a.title}</strong>
          <p>
            <span className={s.toneDot} style={{ background: TONE_COLOR[a.tone] }} />
            {a.toneLabel} · {a.source} · {a.time}
          </p>
        </article>
      ))}
    </>
  );
}

/**
 * 기사 피드 — 논조 뱃지가 붙은 카드 목록. 비면 왜 비었는지 말해 준다.
 * 출처: 아카이브/app.js articleFeedMarkup()
 *
 * @param {{articles: object[], emptyTitle?: string, emptyDesc?: string}} props
 */
export default function ArticleFeed({
  articles,
  emptyTitle = '조건에 맞는 기사가 없습니다.',
  emptyDesc = '논조 필터를 변경해 보세요.',
}) {
  if (!articles.length) {
    return (
      <div className={s.feed}>
        <div className={s.emptyArticles}>
          <strong>{emptyTitle}</strong>
          <p>{emptyDesc}</p>
        </div>
      </div>
    );
  }
  return (
    <div className={s.feed}>
      {articles.map((a) => (
        <article className={s.feedCard} key={a.id ?? a.title}>
          <div>
            <span className={`${s.articleTone} ${s[a.tone]}`}>{a.toneLabel}</span>
            <span>
              {a.source} · {a.time}
            </span>
          </div>
          <strong>{a.title}</strong>
          <p>{a.summary}</p>
          {a.url ? <a href={a.url} target="_blank" rel="noopener noreferrer">기사 원문 보기 →</a> : <span>원문 링크가 제공되지 않았습니다.</span>}
        </article>
      ))}
    </div>
  );
}

/** 결과 머리말 — 무엇을 몇 건 보여주는지 */
export function ResultHead({ title, count }) {
  return (
    <div className={s.resultHead}>
      <strong>{title}</strong>
      <span>{count}</span>
    </div>
  );
}

/**
 * 논조 필터 바.
 * 출처: 아카이브/app.js .secondary-filter-bar
 *
 * 원본에는 정렬(최신순⌄)과 기간(최근 24시간⌄) 버튼도 있었지만
 * 아무 동작도 하지 않는 버튼이라 뺐다 — 누를 수 있어 보이는데 아무 일도 안 일어나면
 * 필터 전체를 못 믿게 된다.
 */
export function ArticleFilterBar({ tone = 'all', onTone }) {
  const tones = [
    ['all', '논조 전체'],
    ['positive', '긍정'],
    ['neutral', '중립'],
    ['negative', '부정'],
  ];
  return (
    <div className={s.filterBar}>
      <div className={s.toneFilter} role="group" aria-label="기사 논조 필터">
        {tones.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tone === id ? s.on : ''}
            aria-pressed={tone === id}
            onClick={() => onTone?.(id)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
