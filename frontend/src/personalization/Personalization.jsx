import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../data/api.js';
import { useResource } from '../data/useResource.js';
import { dateLabel, safeUrl } from '../data/responseAdapters.js';
import { httpNewsSource } from '../news/newsSource.js';
import { accountApi } from './accountApi.js';
import { readSsafyCallback } from './ssafyOAuth.js';
import { AuthForm, PasswordForm } from './AccountForms.jsx';
import { accountStorageKey, emptyInterests, parseInterests, loadPersonalNews } from './model.js';
import s from './Personalization.module.css';

const Context = createContext(null);
export const usePersonalization = () => useContext(Context);
export function PersonalizationProvider({ children }) {
  const [session, setSession] = useState(null);
  const [checking, setChecking] = useState(true);
  const [sessionError, setSessionError] = useState('');
  const [storageError, setStorageError] = useState('');
  const [notice, setNotice] = useState('');
  const [panel, setPanel] = useState(null);
  const revision = useRef(0);
  const user = session?.user || null;
  const interests = session?.interests || emptyInterests();
  async function refreshSession(signal) {
    const version = ++revision.current;
    setChecking(true); setSessionError('');
    try {
      const current = await accountApi.me(signal);
      if (!current?.id || !current.email) throw new Error('사용자 정보를 확인하지 못했습니다. 다시 로그인해 주세요.');
      if (version !== revision.current) return null;
      setSession((old) => {
        if (old?.user.id === current.id) return { ...old, user: current };
        let saved = emptyInterests();
        try { saved = parseInterests(localStorage.getItem(accountStorageKey(current.id))); } catch { /* Storage is optional. */ }
        return { user: current, interests: saved };
      });
      return current;
    } catch (error) {
      if (signal?.aborted || version !== revision.current) return null;
      setSession(null);
      if (error.status !== 401) setSessionError(error.message);
      return null;
    } finally { if (version === revision.current) setChecking(false); }
  }
  useEffect(() => {
    const controller = new AbortController();
    refreshSession(controller.signal);
    return () => { controller.abort(); revision.current++; };
  }, []);
  useEffect(() => {
    let callback;
    try { callback = readSsafyCallback(window.location.search); }
    catch (error) {
      const clean = new URL(window.location.href);
      ['code', 'state', 'error', 'error_description'].forEach((key) => clean.searchParams.delete(key));
      window.history.replaceState(null, '', `${clean.pathname}${clean.search}${clean.hash}`);
      setNotice(error.message); setPanel('profile'); setChecking(false);
      return;
    }
    if (!callback) return;
    // Remove the one-time authorization code before the request so a refresh or
    // React StrictMode remount cannot exchange it twice.
    window.history.replaceState(null, '', callback.returnUrl);
    setPanel('profile'); setChecking(true); setNotice('SSAFY 계정을 연결하고 있습니다…');
    accountApi.ssafyLogin(callback.code)
      .then(() => refreshSession())
      .then((current) => {
        if (!current) throw new Error('로그인 세션을 확인하지 못했습니다.');
        setNotice(''); setPanel('profile');
      })
      .catch((error) => { setSession(null); setSessionError(error.message); setNotice(''); setPanel('profile'); setChecking(false); });
  }, []);
  useEffect(() => {
    if (!session) return;
    try { localStorage.setItem(accountStorageKey(session.user.id), JSON.stringify(session.interests)); setStorageError(''); }
    catch { setStorageError('관심사를 저장하지 못했습니다. 새로고침하면 설정이 사라질 수 있습니다.'); }
  }, [session]);
  function expire(message = '로그인이 만료되었습니다. 다시 로그인해 주세요.') {
    revision.current++; setSession(null); setChecking(false); setNotice(message); setPanel('profile');
  }
  const toggle = (kind, item) => {
    if (!user) { setPanel('profile'); return; }
    setSession((old) => {
      if (!old) return old;
      const list = old.interests[kind];
      const exists = list.some((entry) => entry.id === item.id);
      if (!exists && list.length >= (kind === 'countries' ? 5 : 10)) return old;
      return { ...old, interests: { ...old.interests, [kind]: exists ? list.filter((entry) => entry.id !== item.id) : [...list, item] } };
    });
  };
  const openPanel = (next) => { setNotice(''); setPanel(next); if (user) refreshSession(); };
  const logout = async () => { await accountApi.logout(); revision.current++; setSession(null); setPanel(null); };
  const context = { user, interests, toggle, panel, setPanel: openPanel, checking, logout };
  return <Context.Provider value={context}>{children}{panel && <Modal title={checking ? '계정 확인' : !user ? '로그인 / 회원가입' : panel === 'inbox' ? '뉴스 구독함' : '마이페이지'} close={() => setPanel(null)} inbox={!!user && panel === 'inbox'}>
    {checking ? <p role="status">로그인 상태를 확인하고 있습니다…</p> : !user ? <>
      {sessionError && <p className={s.error} role="alert">{sessionError} <button type="button" onClick={() => refreshSession()}>다시 확인</button></p>}
      <AuthForm notice={notice} onLogin={async () => { const current = await refreshSession(); if (!current) { setSessionError('로그인 세션을 확인하지 못했습니다. 연결 상태를 확인해 주세요.'); return; } setPanel('profile'); setNotice(''); }} />
    </> : panel === 'inbox' ? <Inbox key={user.id} interests={interests} onProfile={() => setPanel('profile')} /> : <Profile key={user.id} user={user} interests={interests} toggle={toggle} storageError={storageError} onInbox={() => setPanel('inbox')} onExpired={expire} onLogout={logout} />}
  </Modal>}</Context.Provider>;
}

export function CloseIcon() { return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>; }
function Modal({ title, close, inbox, children }) {
  const dialog = useRef(null);
  const closeButton = useRef(null);
  useEffect(() => { closeButton.current?.focus(); }, [title]);
  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current.showModal();
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return createPortal(<dialog ref={dialog} className={`${s.dialog} ${inbox ? s.inbox : ''}`} aria-labelledby="personal-title" onCancel={close} onClick={(event) => {
    if (event.target !== dialog.current) return;
    const box = dialog.current.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
  }}><header className={s.heading}><div><span className={s.eyebrow}>What In The World</span><h2 id="personal-title">{title}</h2></div><button ref={closeButton} type="button" className={s.close} onClick={close} aria-label="닫기" autoFocus><CloseIcon /></button></header><div className={s.body}>{children}</div></dialog>, document.body);
}

export function InterestButton({ kind, id, name }) {
  const context = usePersonalization();
  if (!context || !id) return null;
  const selected = context.interests[kind].some((item) => item.id === id);
  return <button type="button" className={s.follow} aria-pressed={selected} disabled={context.checking || (!selected && context.interests[kind].length >= 10)} onClick={() => context.toggle(kind, { id, name })}>{selected ? '✓ 관심 등록됨 · 해제' : `＋ 관심 ${kind === 'themes' ? '테마' : '이슈'} 등록`}</button>;
}

function Chips({ items, remove }) {
  return <div className={s.chips}>{items.map((item) => <span className={s.chip} key={item.id}>{item.name}<button type="button" onClick={() => remove(item)} aria-label={`${item.name} 관심 해제`}><CloseIcon /></button></span>)}</div>;
}
function Profile({ user, interests, toggle, storageError, onInbox, onExpired, onLogout }) {
  const [tab, setTab] = useState('interests');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const filters = useResource('subscription-filters', (signal) => httpNewsSource.filters({ signal }));
  return <>
    <div className={s.account}><span className={s.avatar}>{user.email.slice(0, 1).toUpperCase()}</span><div><strong>{user.email}</strong></div><button className={s.textButton} type="button" disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await onLogout(); } catch (err) { if (err.status === 401) onExpired(); else setError(err.message); } finally { setBusy(false); } }}>로그아웃</button></div>
    <div className={s.tabs}><button type="button" aria-pressed={tab === 'interests'} onClick={() => setTab('interests')}>관심사 설정</button><button type="button" aria-pressed={tab === 'password'} onClick={() => setTab('password')}>비밀번호 변경</button></div>
    {error && <p role="alert" className={s.error}>{error}</p>}
    {tab === 'password' ? user.authProvider === 'LOCAL' ? <PasswordForm onExpired={onExpired} onChanged={() => onExpired('비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.')} /> : <p className={s.description}>외부 계정의 비밀번호는 해당 로그인 서비스에서 변경해 주세요.</p> : <>
      <p className={s.description}>관심 있는 테마 키워드를 선택하면 뉴스 구독함에 관련 기사가 모입니다.</p>
      {storageError && <p role="alert" className={s.error}>{storageError}</p>}
      {filters.loading && <p role="status">선택 목록을 불러오는 중…</p>}
      {filters.error && <p role="alert" className={s.error}>{filters.error.message} <button type="button" onClick={filters.retry}>다시 시도</button></p>}
      <section className={s.section}><label className={s.label} htmlFor="interest-theme">테마 키워드 <small>{interests.themes.length}/10</small></label><p className={s.hint}>뉴스를 구독할 테마를 선택하세요. 여러 개를 추가할 수 있습니다.</p>
        <select id="interest-theme" value="" disabled={filters.loading || !filters.data || interests.themes.length >= 10} onChange={(e) => { const item = filters.data.fields.flatMap((f) => f.themes).find((t) => String(t.themeId) === e.target.value); if (item) toggle('themes', { id: item.themeId, name: item.themeName }); }}><option value="" disabled>테마 키워드 선택</option>{(filters.data?.fields || []).map((field) => <optgroup key={field.fieldId} label={field.fieldName}>{field.themes.filter((t) => !interests.themes.some((v) => v.id === t.themeId)).map((t) => <option key={t.themeId} value={t.themeId}>{t.themeName}</option>)}</optgroup>)}</select>
        <Chips items={interests.themes} remove={(item) => toggle('themes', item)} />
      </section>
      {interests.issues.length > 0 && <section className={s.section}><h3>관심 이슈</h3><p className={s.hint}>이슈 상세에서 등록한 항목입니다.</p><Chips items={interests.issues} remove={(item) => toggle('issues', item)} /></section>}
      <button type="button" className={`${s.primary} ${s.inboxLink}`} onClick={onInbox}>뉴스 구독함 보기 →</button>
    </>}
  </>;
}

function Inbox({ interests, onProfile }) {
  const [size, setSize] = useState(12);
  const [selected, setSelected] = useState(null);
  // 'all' 또는 관심 테마 id. 해제된 테마를 가리키면 전체로 돌아간다.
  const [tab, setTab] = useState('all');
  const theme = interests.themes.find((item) => item.id === tab) || null;
  const scope = { countries: [], themes: theme ? [theme] : interests.themes, issues: theme ? [] : interests.issues };
  const news = useResource(`subscriptions:${JSON.stringify(scope)}:${size}`, (signal) => loadPersonalNews(scope, httpNewsSource, api, signal, size));
  const detail = useResource(selected ? `subscription-article:${selected}` : null, (signal) => httpNewsSource.detail(selected, { signal }));
  const count = interests.themes.length + interests.issues.length;
  const pick = (next) => { setTab(next); setSize(12); };
  if (selected) return <><button type="button" className={s.textButton} onClick={() => setSelected(null)}>← 뉴스 구독함</button>{detail.loading && <p role="status">기사를 불러오는 중…</p>}{detail.error && <p role="alert" className={s.error}>{detail.error.message} <button onClick={detail.retry}>다시 시도</button></p>}{detail.data && <article className={s.reader}><h3>{detail.data.articleTitle || '제목 미제공'}</h3><p className={s.hint}>{detail.data.articlePublisher} · {dateLabel(detail.data.publishedAt)}</p><p>{detail.data.summary || '요약이 제공되지 않은 기사입니다.'}</p>{safeUrl(detail.data.url) && <a href={safeUrl(detail.data.url)} target="_blank" rel="noopener noreferrer">기사 원문 보기 ↗</a>}</article>}</>;
  if (!count) return <div className={s.empty}><h3>구독할 테마를 골라주세요</h3><button type="button" className={s.primary} onClick={onProfile}>구독 관리</button></div>;
  return <>
    <div className={s.inboxBar}>
      <div className={s.inboxTabs} role="tablist" aria-label="구독 테마">
        <button type="button" role="tab" aria-selected={!theme} onClick={() => pick('all')}>전체</button>
        {interests.themes.map((item) => <button type="button" role="tab" key={item.id} aria-selected={tab === item.id} onClick={() => pick(item.id)}>#{item.name}</button>)}
      </div>
      <div className={s.inboxActions}>
        <button type="button" className={s.textButton} disabled={news.loading} onClick={news.retry}>새로고침</button>
        <button type="button" className={s.textButton} onClick={onProfile}>구독 관리</button>
      </div>
    </div>
    {news.loading && <p role="status">구독 뉴스를 불러오는 중…</p>}
    {news.error && <p className={s.error} role="alert">{news.error.message}</p>}
    {news.data?.failed.length > 0 && <p className={s.error} role="alert">불러오지 못한 구독: {news.data.failed.join(', ')}. 새로고침으로 다시 시도해 주세요.</p>}
    {news.data?.articles.map((article) => <article className={s.newsItem} key={article.articleId}>{!theme && <div className={s.matches}>{article.matches.map((name) => <span key={name}>{name}</span>)}</div>}<button type="button" className={s.articleTitle} onClick={() => setSelected(article.articleId)}>{article.articleTitle || '제목 미제공 · 기사 보기'}</button><p className={s.hint}>{article.countryName ? `${article.countryName} · ` : ''}{article.articlePublisher} · {dateLabel(article.publishedAt)}</p></article>)}
    {!news.loading && news.data && !news.data.articles.length && !news.data.failed.length && <p className={s.empty}>{theme ? `#${theme.name} 에 해당하는 기사가 아직 없습니다.` : '선택한 관심사에 해당하는 기사가 아직 없습니다.'}</p>}
    {news.data?.hasMore && size < 100 && <button type="button" disabled={news.loading} className={s.secondary} onClick={() => setSize((old) => Math.min(100, old + 12))}>이전 뉴스 더 보기</button>}
    <p className={s.footnote}>{theme ? '선택한 테마의' : '테마별'} 최근 {size}건을 조회합니다.{size === 100 && ' 더 오래된 기사는 전체 뉴스에서 확인하세요.'}{!theme && interests.issues.length > 0 && ' 관심 이슈는 대표 기사 최대 10건을 함께 표시합니다.'}</p>
  </>;
}
