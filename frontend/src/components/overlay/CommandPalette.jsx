import { useEffect, useRef, useState } from 'react';
import s from './minimal.module.css';

/**
 * 커맨드 팔레트 — ⌘K / Ctrl+K로 열리는 국가 검색.
 * 상단바 검색 버튼과 단축키가 같은 창을 연다.
 * 출처: 아카이브/index.html .command-palette + app.js openPalette()
 *
 * @param {{open: boolean, onClose: () => void,
 *          quick: {flag: string, name: string, count: string}[],
 *          onSelect: (name: string) => void, placeholder?: string}} props
 */
export default function CommandPalette({
  open,
  onClose,
  quick = [],
  onSelect,
  placeholder = '분석할 국가를 검색하세요',
}) {
  const inputRef = useRef(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (open) {
      setQuery('');
      const id = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [open]);

  if (!open) return null;

  const q = query.trim().toLowerCase();
  const list = q ? quick.filter((c) => c.name.toLowerCase().includes(q)) : quick;

  return (
    <div className={`${s.palette} ${s.open}`} aria-hidden="false">
      <button type="button" className={s.backdrop} aria-label="검색 닫기" onClick={onClose} />
      <div className={s.card} role="dialog" aria-modal="true" aria-label="국가 검색">
        <div className={s.inputWrap}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4 4" />
          </svg>
          <input
            ref={inputRef}
            type="search"
            placeholder={placeholder}
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className={s.kbd}>ESC</kbd>
        </div>
        <p>빠른 선택</p>
        {!list.length && <p role="status">검색 결과가 없습니다.</p>}
        {list.map((c) => (
          <button
            key={c.name}
            type="button"
            className={s.quick}
            onClick={() => {
              onSelect(c.name);
              onClose();
            }}
          >
            <span>{c.flag}</span>
            <b>{c.name}</b>
            <small>{c.count}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * ⌘K / Ctrl+K 로 열고 ESC로 닫는 훅.
 * 팔레트를 쓰는 화면 어디에서든 같은 단축키를 붙일 수 있다.
 */
export function usePaletteHotkey(onOpen, onClose) {
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onOpen();
      }
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onOpen, onClose]);
}
