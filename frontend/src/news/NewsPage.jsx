import { useEffect, useMemo, useRef, useState } from 'react';
import { useResource } from '../data/useResource.js';
import { dateLabel, flagOf, safeUrl } from '../data/responseAdapters.js';
import { countryMetadata } from '../data/countries.js';
import { newsSource, isMockNews } from './newsSource.js';
import { PAGE_SIZE, newsSearch, queryError, readNewsQuery } from './newsQuery.js';
import s from './NewsPage.module.css';

function Failure({ error, retry }) {
  return <div className={s.empty} role="alert"><p>{error.message}</p><button onClick={retry}>다시 시도</button></div>;
}

const flagImages = Object.fromEntries(countryMetadata.map(({ code, flagImage }) => [code, flagImage]));

function CountryFlag({ code }) {
  const countryCode = code?.toUpperCase();
  const flagImage = flagImages[countryCode];
  return <span className={s.countryFlag} aria-hidden="true">
    {flagImage ? <img src={flagImage} alt="" /> : flagOf(countryCode)}
  </span>;
}

function ArticleModal({ id, onClose, source, asOf }) {
  const dialog = useRef(null);
  const article = useResource(`news-detail:${asOf}:${id}`, (signal) => source.detail(id, { signal, asOf }));
  useEffect(() => {
    const opener = document.activeElement;
    const element = dialog.current;
    element.showModal();
    return () => { element.close(); opener?.focus(); };
  }, []);
  const data = article.data;
  const url = safeUrl(data?.url);
  return <dialog ref={dialog} className={s.modal} aria-labelledby="news-article-title" onCancel={(e) => { e.preventDefault(); onClose(); }}>
    <div className={s.modalTop}><span>ARTICLE BRIEF</span><button autoFocus onClick={onClose} aria-label="기사 상세 닫기">×</button></div>
    <h2 id="news-article-title">{data?.articleTitle || (article.loading ? '기사를 불러오는 중…' : '기사 상세')}</h2>
    {article.error ? <Failure error={article.error} retry={article.retry} /> : data ? <>
      <p className={s.meta}><CountryFlag code={data.countryCode} />{data.countryName} · {data.articlePublisher || '매체 미상'} · {dateLabel(data.publishedAt)}</p>
      <div className={s.summary}><h3>기사 요약</h3><p>{data.summary?.trim() || '제공된 기사 요약이 없습니다.'}</p></div>
      {isMockNews && <p className={s.demo}>실제 보도가 아닌 예시입니다. 원문 링크는 예시 사이트로 연결됩니다.</p>}
      <div className={s.modalBottom}>{url ? <a href={url} target="_blank" rel="noopener noreferrer">원문 읽기 ↗</a> : <span>제공된 원문 링크가 없습니다.</span>}<span>원문은 새 탭에서 열립니다.</span></div>
    </> : <p role="status">요약을 불러오고 있습니다.</p>}
  </dialog>;
}

export default function NewsPage({ search, navigate, source = newsSource, asOf }) {
  const query = useMemo(() => readNewsQuery(search), [search]);
  const [draft, setDraft] = useState(query);
  const [selected, setSelected] = useState(null);
  const [formError, setFormError] = useState('');
  const results = useRef(null);
  const filters = useResource(`news-filters:${asOf}`, (signal) => source.filters({ signal, asOf }));
  const error = queryError(query, filters.data);
  const list = useResource(filters.data && !error ? `news-list:${asOf}:${JSON.stringify(query)}` : null,
    (signal) => source.list({ ...query, size: PAGE_SIZE }, { signal, asOf }));
  useEffect(() => { setDraft(query); setFormError(''); setSelected(null); }, [query]);
  const fields = filters.data?.fields || [];
  const themes = (draft.fieldId ? fields.filter((f) => String(f.fieldId) === draft.fieldId) : fields).flatMap((f) => f.themes);
  const update = (key, value) => setDraft((old) => ({ ...old, [key]: value, ...(key === 'fieldId' ? { themeId: '' } : {}) }));
  const apply = (e) => {
    e.preventDefault();
    const invalid = queryError(draft, filters.data);
    setFormError(invalid);
    if (!invalid) navigate(newsSearch({ ...draft, page: 1 }));
  };
  const reset = () => { setDraft(readNewsQuery('')); setFormError(''); navigate(newsSearch({ page: 1 })); };
  const pageTo = (page) => { navigate(newsSearch({ ...query, page })); results.current?.scrollIntoView({ block: 'start' }); };
  const totalPages = list.data?.totalPages || 0;
  const startPage = Math.max(1, Math.min(query.page - 2, totalPages - 4));
  const pages = Array.from({ length: Math.min(5, totalPages) }, (_, i) => startPage + i);
  return <main className={s.page}>
    <div className={s.content}>
      <div className={s.heading}><div><p className={s.eyebrow}>WORLD NEWS ARCHIVE</p><h1>전체 뉴스<span>.</span></h1><p>세계의 소식을, 원하는 시선으로.<br />국가와 주제를 선택하고 지난 뉴스를 살펴보세요.</p></div>{isMockNews && <span className={s.demoBadge}>데모 데이터</span>}</div>
      <form className={s.filters} onSubmit={apply}>
        <div className={s.filterTitle}><strong>뉴스 찾아보기</strong><button type="button" onClick={reset}>필터 초기화 ↺</button></div>
        <div className={s.filterGrid}>
          <label>국가<select id="news-country-filter" value={draft.countryCode} onChange={(e) => update('countryCode', e.target.value)} disabled={!filters.data}><option value="">전체 국가</option>{filters.data?.countries.map((c) => <option key={c.countryCode} value={c.countryCode}>{c.countryName}</option>)}</select></label>
          <label>분야<select value={draft.fieldId} onChange={(e) => update('fieldId', e.target.value)} disabled={!filters.data}><option value="">전체 분야</option>{fields.map((f) => <option key={f.fieldId} value={f.fieldId}>{f.fieldName}</option>)}</select></label>
          <label>테마<select value={draft.themeId} onChange={(e) => update('themeId', e.target.value)} disabled={!filters.data}><option value="">전체 테마</option>{themes.map((t) => <option key={t.themeId} value={t.themeId}>{t.themeName}</option>)}</select></label>
          <label>시작일<input type="date" value={draft.from} onChange={(e) => update('from', e.target.value)} /></label>
          <label>종료일<input type="date" value={draft.to} onChange={(e) => update('to', e.target.value)} /></label>
          <button className={s.submit} disabled={!filters.data} type="submit">조회하기</button>
        </div>
        <p className={s.hint}>국가는 기사 발행 국가 기준 · 기간을 비워두면 전체 기간을 조회합니다.</p>
        {(formError || error) && <p className={s.error} role="alert">{formError || error}</p>}
      </form>
      {filters.error && <Failure error={filters.error} retry={filters.retry} />}
      <section ref={results} aria-label="뉴스 검색 결과" aria-busy={filters.loading || list.loading}>
        <div className={s.resultsHead}><h2>뉴스 목록 <span>{list.data ? list.data.totalElements.toLocaleString('ko-KR') : '—'}</span></h2><span>최신순 · 페이지당 {PAGE_SIZE}개</span></div>
        {filters.loading || list.loading ? <div className={s.empty} role="status">뉴스를 불러오고 있습니다…</div>
          : list.error ? <Failure error={list.error} retry={list.retry} />
          : !error && list.data && <>
            {!list.data.items.length ? <div className={s.empty}><h3>{query.page > Math.max(totalPages, 1) ? '존재하지 않는 페이지입니다.' : '조건에 맞는 뉴스가 없습니다.'}</h3><p>다른 국가나 주제를 선택하거나 조회 기간을 넓혀보세요.</p><button onClick={query.page > 1 ? () => pageTo(1) : reset}>{query.page > 1 ? '첫 페이지로' : '필터 초기화'}</button></div>
              : <div className={s.grid}>{list.data.items.map((article) => <button key={article.articleId} className={s.card} onClick={() => setSelected(article.articleId)}>
                <div className={s.cardTop}><span className={s.countryBadge}><CountryFlag code={article.countryCode} />{article.countryName}</span><span>{article.fieldName} / {article.themeName}</span></div>
                <h3>{article.articleTitle || '제목 없음'}</h3>
                <p>{article.summary || '기사를 선택해 상세 내용을 확인하세요.'}</p>
                <div className={s.cardBottom}><span>{article.articlePublisher || '매체 미상'}<time dateTime={article.publishedAt}>{dateLabel(article.publishedAt)}</time></span><span aria-hidden="true">↗</span></div>
              </button>)}</div>}
            {totalPages > 0 && query.page <= totalPages && <nav className={s.pagination} aria-label="뉴스 페이지">
              <button disabled={query.page <= 1} onClick={() => pageTo(1)} aria-label="첫 페이지">«</button>
              <button disabled={query.page <= 1} onClick={() => pageTo(query.page - 1)} aria-label="이전 페이지">‹</button>
              {pages.map((page) => <button key={page} aria-current={page === query.page ? 'page' : undefined} onClick={() => pageTo(page)}>{page}</button>)}
              <button disabled={query.page >= totalPages} onClick={() => pageTo(query.page + 1)} aria-label="다음 페이지">›</button>
              <button disabled={query.page >= totalPages} onClick={() => pageTo(totalPages)} aria-label="마지막 페이지">»</button>
              <span>{query.page} / {totalPages}</span>
            </nav>}
          </>}
      </section>
    </div>
    {selected && <ArticleModal asOf={asOf} key={selected} id={selected} source={source} onClose={() => setSelected(null)} />}
  </main>;
}
