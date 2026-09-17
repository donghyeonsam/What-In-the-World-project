import { useEffect, useRef, useState } from 'react';
import s from './HeaderMinimal.module.css';
import { timeLabel } from '../../timeMachine/timeMachine.js';
import { usePersonalization } from '../../personalization/Personalization.jsx';

const UserIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></svg>;

// 비로그인: 아이콘 → 로그인 모달. 로그인: 아이콘 → 마이페이지 / 로그아웃 드롭다운.
function UserMenu({ personal }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  useEffect(() => {
    if (!open) return;
    const away = (event) => { if (!root.current?.contains(event.target)) setOpen(false); };
    const key = (event) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', away);
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', key); };
  }, [open]);
  if (!personal.user) return <button type="button" className={s.iconButton} aria-label="로그인 / 회원가입" title="로그인 / 회원가입" aria-haspopup="dialog" aria-expanded={personal.panel === 'profile'} onClick={() => personal.setPanel('profile')}><UserIcon /></button>;
  const pick = (action) => { setOpen(false); action(); };
  return <div className={s.menuRoot} ref={root}>
    <button type="button" className={s.iconButton} aria-label="계정 메뉴" title={personal.user.email} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}><UserIcon /></button>
    {open && <div className={s.menu} role="menu">
      <p className={s.menuEmail}>{personal.user.email}</p>
      <button type="button" role="menuitem" onClick={() => pick(() => personal.setPanel('profile'))}>마이페이지</button>
      <button type="button" role="menuitem" onClick={() => pick(() => personal.logout().catch(() => personal.setPanel('profile')))}>로그아웃</button>
    </div>}
  </div>;
}

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4 4" />
  </svg>
);

/**
 * 라이트 미니멀 상단바 — 제호 + 중앙 라우트 탭 + 검색 트리거.
 * 출처: 아카이브/index.html .topbar
 *
 * @param {{brand?: string, routes?: {id: string, label: string}[], route?: string,
 *          onRoute?: (id: string) => void, onSearch?: () => void,
 *          searchLabel?: string, shortcut?: string}} props
 */
export default function HeaderMinimal({
  brand = 'What In the World!',
  routes = [
    { id: 'global', label: '글로벌 동향' },
    { id: 'country', label: '국가 분석' },
    { id: 'news', label: '전체 뉴스' },
  ],
  route = 'global',
  onRoute,
  onSearch,
  showSearch = true,
  asOf = null,
  timeMachineOpen = false,
  onTimeMachine,
  onLive,
  searchLabel = '국가 검색',
  shortcut = '⌘ K',
}) {
  const personal = usePersonalization();
  return (
    <header className={s.topbar}>
      <a className={s.brand} href={`${typeof window === 'undefined' ? '/' : window.location.pathname}${asOf ? `?${new URLSearchParams({ asOf })}` : ''}`} aria-label={`${brand} 초기 화면으로 이동`}>
        <img src="/witw_logo_transparent.png" alt={brand} />
      </a>

      <nav className={s.nav} aria-label="주요 메뉴">
        {routes.map((r) => (
          <button
            key={r.id}
            type="button"
            className={`${s.navItem} ${route === r.id ? s.active : ''}`}
            aria-current={route === r.id ? 'page' : undefined}
            onClick={() => onRoute?.(r.id)}
          >
            {r.label}
          </button>
        ))}
        {onTimeMachine && <button type="button" className={`${s.navItem} ${timeMachineOpen ? s.active : ''}`} onClick={onTimeMachine} aria-haspopup="dialog" aria-expanded={timeMachineOpen}>타임머신</button>}
      </nav>

      <div className={s.actions}>
        {asOf && <button className={s.archiveBadge} onClick={onLive} title="현재 시점으로 돌아오기"><span>{timeLabel(asOf)} 기준</span><strong>현재로 ↗</strong></button>}
        {showSearch && <button type="button" className={s.search} onClick={onSearch} aria-label={searchLabel}>
          <SearchIcon />
          <span>{searchLabel}</span>
          <kbd className={s.kbd}>{shortcut}</kbd>
        </button>}
        {personal && <>
          {personal.user && <button type="button" className={s.iconButton} aria-label="뉴스 구독함" title="뉴스 구독함" aria-haspopup="dialog" aria-expanded={personal.panel === 'inbox'} onClick={() => personal.setPanel('inbox')}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16l2 10v5H2v-5L4 5Z" /><path d="M2 15h6l2 3h4l2-3h6M8 9h8M9 12h6" /></svg>
          </button>}
          <UserMenu personal={personal} />
        </>}
      </div>
    </header>
  );
}
