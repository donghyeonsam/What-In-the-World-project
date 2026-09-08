import { useMemo, useRef, useState } from 'react';
import s from './panel.module.css';

/**
 * 테마 선택 패널 + 전체 테마 찾기.
 * 급상승 상위 몇 개는 칩으로 바로 노출하고, 나머지 전체는 검색 팝오버에서 고른다.
 * 목록이 길어질수록 "많이 보여주기"보다 "빨리 찾게 하기"가 낫다는 판단이다.
 * 출처: 아카이브/app.js .theme-filter-panel / .theme-picker
 *
 * @param {{quickThemes: object[], catalog: object[], fields: string[],
 *          selectedIndex?: number|null, selectedTheme?: object|null,
 *          onSelectQuick?: (index: number|null) => void,
 *          onSelectCatalog?: (index: number) => void,
 *          totalLabel?: string}} props
 *   selectedIndex는 quickThemes 기준, selectedTheme은 화면에 표시할 현재 테마.
 */
export default function ThemeFilterPanel({
  quickThemes,
  catalog,
  fields,
  selectedIndex = null,
  selectedTheme = null,
  onSelectQuick,
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
      <div className={s.filterTitle}>
        <div>
          <strong>테마 선택</strong>
          <span>분야별 테마 · 빠른 선택 {quickThemes.length}개</span>
        </div>
        <button
          type="button"
          onClick={() => {
            setOpen(true);
            setTimeout(() => inputRef.current?.focus(), 0);
          }}
        >
          전체 테마 찾기 <b>{totalLabel}</b> →
        </button>
      </div>

      <div className={s.selectedTheme}>
        <span>현재 테마</span>
        <strong>
          {selectedTheme ? `${selectedTheme.field} › ${selectedTheme.name}` : '테마 선택 없음'}
        </strong>
        {selectedTheme && (
          <button type="button" aria-label="테마 선택 해제" onClick={() => onSelectQuick?.(null)}>
            ×
          </button>
        )}
      </div>

      <div className={s.quickThemeList}>
        <button
          type="button"
          className={selectedIndex === null ? s.on : ''}
          onClick={() => onSelectQuick?.(null)}
        >
          선택 해제
        </button>
        {quickThemes.map((theme, index) => (
          <button
            key={theme.name}
            type="button"
            className={selectedIndex === index ? s.on : ''}
            onClick={() => onSelectQuick?.(index)}
          >
            {theme.name}
            <b>{theme.rise}</b>
          </button>
        ))}
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
