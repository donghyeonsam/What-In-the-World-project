import { useEffect, useRef } from 'react';
import Icon from './Icon.jsx';
import { countryByCode, toneLabels } from '../data/demo.js';
export const fmt = n => n == null ? '—' : Number(n).toLocaleString('ko-KR');
export function date(value) { if (!value) return '시각 미제공'; const d = new Date(value); return Number.isNaN(+d) ? '시각 미제공' : d.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul' }); }
export function Source({ demo, children }) { return <span className={`source ${demo ? 'demo' : 'live'}`}><i/>{children || (demo ? '데모 데이터' : '실제 API')}</span>; }
export function Empty({ title = '조건에 맞는 결과가 없습니다', text = '다른 국가나 테마를 선택해 보세요.', action }) { return <div className="empty"><Icon name="search" size={30}/><h3>{title}</h3><p>{text}</p>{action}</div>; }
export function Resource({ resource, children }) {
  if (resource.error) return <div className="error-state" role="alert"><strong>데이터를 불러오지 못했어요</strong><p>{resource.error}</p><button className="button secondary" onClick={resource.retry}><Icon name="refresh" size={16}/>다시 시도</button><small>실제 API 오류를 데모 데이터로 대체하지 않습니다.</small></div>;
  if (resource.loading || !resource.data) return <div className="skeleton" role="status" aria-label="데이터 불러오는 중"><div/><div/><div/><span>데이터를 불러오는 중…</span></div>;
  return children(resource.data);
}
export function Modal({ title, onClose, children, wide = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement, old = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.focus();
    const handler = e => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab') {
        const items = [...ref.current.querySelectorAll('button,a[href],input,select,[tabindex="0"]')].filter(el => !el.disabled && el.offsetParent !== null);
        const first = items[0], last = items.at(-1);
        if (!first) { e.preventDefault(); return; }
        if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    const el = ref.current; el.addEventListener('keydown', handler);
    return () => { document.body.style.overflow = old; el.removeEventListener('keydown', handler); previous?.focus(); };
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}><section className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}><div className="modal-top"><span>{title}</span><button className="icon-button" onClick={onClose} aria-label="닫기"><Icon name="close"/></button></div>{children}</section></div>;
}
export function ArticleList({ articles, onOpen, onSave, saved = [], compact = false }) {
  if (!articles.length) return <Empty/>;
  return <div className={`article-list ${compact ? 'compact' : ''}`}>{articles.map((article, i) => <article key={article.id} className="article-row"><span className="article-index">{String(i + 1).padStart(2, '0')}</span><div className="article-content"><div className="article-meta"><span>{countryByCode(article.countryCode)?.flag} {article.publisher}</span><span className={`tone-dot ${article.tone}`}>{toneLabels[article.tone] || '분석 없음'}</span></div><button className="article-title" onClick={() => onOpen(article)}>{article.title}</button><div className="article-bottom"><time>{date(article.publishedAt)} KST</time>{article.demo && <span>가상 기사</span>}<button onClick={() => onOpen(article)} aria-label={`${article.title} 읽기`}>읽기 <Icon name="arrow" size={14}/></button></div></div><button className={`icon-button save ${saved.includes(article.id) ? 'saved' : ''}`} onClick={() => onSave(article)} aria-label={`${article.title} ${saved.includes(article.id) ? '저장 취소' : '저장'}`} aria-pressed={saved.includes(article.id)}><Icon name="bookmark" size={18}/></button></article>)}</div>;
}
export function Trend({ values = [], label = '시간별 기사량' }) { const max = Math.max(...values, 1); return <div className="trend" role="img" aria-label={`${label}: ${values.join(', ')}건`}>{values.map((v, i) => <i key={i} style={{ height: `${Math.max(3, v / max * 100)}%` }} title={`${i + 1}번째 시간 구간 · ${v}건`}/>)}</div>; }
