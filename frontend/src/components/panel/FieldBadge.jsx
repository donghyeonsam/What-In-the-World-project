import s from './panel.module.css';

const styles = [
  { match: /경제|금융|무역/, color: '#e7c394', path: 'M4 17V11M10 17V7M16 17V3M2 20H21' },
  { match: /산업|기술|과학/, color: '#a9c9f5', path: 'M7 7H17V17H7ZM10 10H14V14H10ZM10 3V7M14 3V7M10 17V21M14 17V21M3 10H7M3 14H7M17 10H21M17 14H21' },
  { match: /외교|안보|정치|국제/, color: '#c6b8ee', path: 'M12 3L20 6V12C20 17 12 21 12 21S4 17 4 12V6ZM8 11L11 14L16 9' },
  { match: /환경|기후/, color: '#a9cfb2', path: 'M5 19C2 8 10 3 20 4C21 15 16 20 5 19ZM5 19L15 9' },
  { match: /사회|보건/, color: '#91ced5', path: 'M9 11A4 4 0 1 0 9 3A4 4 0 0 0 9 11ZM2 21V18A7 7 0 0 1 16 18V21M17 4A4 4 0 0 1 17 12M19 15A6 6 0 0 1 22 20' },
  { match: /문화|스포츠|예술/, color: '#d8b5ce', path: 'M12 3L15 9L22 10L17 15L18 22L12 19L6 22L7 15L2 10L9 9Z' },
];
const fallback = { color: '#b1c2d2', path: 'M3 4H12L21 13L13 21L3 11ZM7 8H7.01' };

export default function FieldBadge({ field, theme }) {
  if (!field) return null;
  const style = styles.find(({ match }) => match.test(field)) || fallback;
  return <span className={s.fieldBadge} style={{ '--field-color': style.color }} aria-label={theme ? `${field} · 테마: ${theme}` : field}>
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d={style.path} />
    </svg>
    <span>{field}</span>
    {theme && <span className={s.fieldTooltip} role="tooltip">테마 · {theme}</span>}
  </span>;
}
