import { useMemo, useRef, useState } from 'react';
import s from './panel.module.css';

/**
 * 테마 선택 패널 + 전체 테마 찾기.
 * 출처: 아카이브/app.js .theme-filter-panel / .theme-picker
 *
 * @param {{catalog: object[], fields: string[], selectedTheme?: object|null,
 *          onSelectCatalog?: (index: number) => void,
 *          totalLabel?: string}} props
 *   selectedTheme은 화면에 표시할 현재 테마.
 */
export default function ThemeFilterPanel({
  catalog,
  fields,
  selectedTheme = null,
  onSelectCatalog,
  totalLabel = '128',
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [field, setField] = useState('all');
  const inputRef = useRef(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog
      .map((t, i) => ({ t, i }))
      .filter(
        ({ t }) =>
          (field === 'all' || t.field === field) && t.name.toLowerCase().includes(q),
      );
  }, [catalog, field, query]);

  return (
    <section className={s.themeFilterPanel}>
      <div className={s.themeToolbar}>
        <div className={s.themeSummary}>
          {selectedTheme?.field && <span>{selectedTheme.field}</span>}
          <strong>{selectedTheme?.name || '테마를 선택해 주세요'}</strong>
        </div>
        <button
          type="button"
          className={s.themeSearchButton}
          aria-expanded={open}
          onClick={() => {
            setOpen(true);
            setTimeout(() => inputRef.current?.focus(), 0);
          }}
        >
          테마 검색 <span aria-hidden="true">→</span>
        </button>
      </div>

      {open && (
        <div className={s.picker}>
          <div className={s.pickerHead}>
            <div>
              <strong>전체 테마 찾기</strong>
              <span>분야별 전체 {totalLabel}개 테마</span>
            </div>
            <button type="button" aria-label="테마 찾기 닫기" onClick={() => setOpen(false)}>
              ×
            </button>
          </div>

          <input
            ref={inputRef}
            className={s.searchInput}
            type="search"
            placeholder="테마 이름 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          <div className={s.categories}>
            <button
              type="button"
              className={field === 'all' ? s.on : ''}
              onClick={() => setField('all')}
            >
              전체 분야
            </button>
            {fields.map((f) => (
              <button
                key={f}
                type="button"
                className={field === f ? s.on : ''}
                onClick={() => setField(f)}
              >
                {f}
              </button>
            ))}
          </div>

          <div className={s.pickerList}>
            {filtered.map(({ t, i }) => (
              <button
                key={t.name}
                type="button"
                onClick={() => {
                  setOpen(false);
                  onSelectCatalog?.(i);
                }}
              >
                <span>
                  <strong>{t.name}</strong>
                  <small>
                    분야: {t.field} · {t.count}
                  </small>
                </span>
                <b>{t.rise}</b>
              </button>
            ))}
          </div>

          <p className={s.pickerNote}>{filtered.length ? `${filtered.length}개 테마를 찾았습니다.` : '검색 조건에 맞는 테마가 없습니다.'}</p>
        </div>
      )}
    </section>
  );
}
