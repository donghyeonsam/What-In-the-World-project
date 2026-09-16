import s from './HeaderMinimal.module.css';

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
  searchLabel = '국가 검색',
  shortcut = '⌘ K',
}) {
  return (
    <header className={s.topbar}>
      <a className={s.brand} href="#" aria-label={`${brand} 홈`} onClick={(e) => e.preventDefault()}>
        <img src="/witw_logo.png" alt={brand} />
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
      </nav>

      <div className={s.actions}>
        <button type="button" className={s.search} onClick={onSearch} aria-label={searchLabel}>
          <SearchIcon />
          <span>{searchLabel}</span>
          <kbd className={s.kbd}>{shortcut}</kbd>
        </button>
      </div>
    </header>
  );
}
