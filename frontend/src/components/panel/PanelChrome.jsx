import s from './panel.module.css';

/** 패널 맨 위 한 줄 — 왼쪽 라벨 + 오른쪽 기준 표시.
    결정표 6번에서 '동작하지 않는 기간 선택 버튼'을 버리기로 했으므로 버튼이 아니라 라벨이다. */
export function PanelTopline({ label, range = '최근 24시간' }) {
  return (
    <div className={s.topline}>
      <span className={s.label}>{label}</span>
      <span className={s.range}>{range}</span>
    </div>
  );
}

/** 제목 + 설명 + 갱신 시각 */
export function PanelHeading({ title, desc, updated }) {
  return (
    <div className={s.heading}>
      <div>
        <h2>{title}</h2>
        {desc && <p>{desc}</p>}
      </div>
      {updated && <span className={s.updated}>{updated}</span>}
    </div>
  );
}

/** 하위 화면 제목 (뒤로 가기 아래) */
export function SubHeading({ title, desc }) {
  return (
    <div className={s.subheading}>
      <h2>{title}</h2>
      {desc && <p>{desc}</p>}
    </div>
  );
}

/** 섹션 제목 — 오른쪽에 보조 설명 또는 '전체 보기' 버튼 */
export function SectionTitle({ title, note, action, help }) {
  return (
    <div className={s.sectionTitle}>
      <div className={s.sectionTitleMain}>
        <h3>{title}</h3>
        {help && <span className={s.helpWrap} aria-label={help}>
          <span className={s.helpIcon} aria-hidden="true">!</span>
          <span className={s.helpTooltip} role="tooltip">{help}</span>
        </span>}
      </div>
      {action ? (
        <button type="button" onClick={action.onClick}>
          {action.label}
        </button>
      ) : (
        note && <span>{note}</span>
      )}
    </div>
  );
}

/** 뒤로 가기 */
export function BackLink({ children, onClick }) {
  return (
    <button type="button" className={s.back} onClick={onClick}>
      {children}
    </button>
  );
}

/**
 * 분류 경로 — 지금 보는 것이 어디에 있는지 알려주고, 조각을 눌러 그 지점으로 올라간다.
 * 출처: 아카이브/app.js .taxonomy-path
 *
 * 뒤로가기를 여러 번 누르는 대신 한 번에 점프하는 길이다.
 * onClick이 없는 조각은 갈 화면이 없다는 뜻이므로 글자로만 둔다(예: 분야).
 *
 * @param {{items: {label: string, value?: string, onClick?: () => void}[]}} props
 */
export function TaxonomyPath({ items }) {
  return (
    <nav className={s.taxonomyPath} aria-label="분류 경로">
      {items.map((it, i) => (
        <span key={`${i}-${it.label}-${it.value ?? ''}`} style={{ display: 'contents' }}>
          {i > 0 && <i>›</i>}
          <span>{it.label}</span>
          {it.value &&
            (it.onClick ? (
              <button type="button" className={s.crumb} onClick={it.onClick}>
                {it.value}
              </button>
            ) : (
              <b>{it.value}</b>
            ))}
        </span>
      ))}
    </nav>
  );
}

/** 국가 아이덴티티 — 큰 국기 + 국명 + 매체 수 */
export function CountryIdentity({ flag, flagImage, flagClass, name, meta }) {
  return (
    <div className={s.identity}>
      <span className={s.largeFlag}>
        {flagImage ? <img src={flagImage} alt="" /> : flagClass ? <i className={flagClass} aria-hidden="true" /> : flag}
      </span>
      <div>
        <h2>{name}</h2>
        {meta && <p>{meta}</p>}
      </div>
    </div>
  );
}

/** 구분선 겸 소제목 */
export function Divider({ children }) {
  return <div className={s.divider}>{children}</div>;
}

/** KPI 2칸 */
export function KpiCards({ items }) {
  return (
    <div className={s.kpiGrid}>
      {items.map((k, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <div className={s.kpiCard} key={i}>
          <small>{k.label}</small>
          <strong>
            {k.value}
            {k.unit && <em>{k.unit}</em>}
          </strong>
          {k.trend && <span className={s.trend}>{k.trend}</span>}
        </div>
      ))}
    </div>
  );
}

/**
 * 분야 칩 — 분류 체계의 입구.
 * 대시보드는 이슈 TOP으로 바로 뛰는 지름길이라, 분야→테마→이슈를 위에서부터 밟고 싶은
 * 사람에게는 들어갈 문이 따로 있어야 한다.
 */
export function FieldChips({ fields, onSelect }) {
  return (
    <div className={s.tagRow}>
      {fields.map((f) => (
        <button key={f.id} type="button" className={s.fieldChip} onClick={() => onSelect(f.id)}>
          {f.name}
          <b>테마 {f.themeCount}</b>
          <em>이슈 {f.issueCount}</em>
        </button>
      ))}
    </div>
  );
}

/** 급상승 태그 줄 */
export function TrendTags({ tags }) {
  return (
    <div className={s.tagRow}>
      {tags.map((t) => (
        <span className={s.trendTag} key={t.label}>
          {t.label} <b>{t.value}</b>
        </span>
      ))}
    </div>
  );
}

/** 원문 미저장 고지 — 결정표 6번에서 가져가기로 한 태도 */
export function PolicyNote({ children }) {
  return <p className={s.policy}>{children}</p>;
}

/** 실시간으로 오르는 값 앞에 붙는 점 */
export function LiveDot() {
  return <i className={s.liveDot} aria-hidden="true" />;
}
