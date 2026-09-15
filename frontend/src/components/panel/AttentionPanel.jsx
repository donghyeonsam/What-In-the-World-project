import s from './panel.module.css';
import { SectionTitle } from './PanelChrome.jsx';

/**
 * 국가 관심도 요약 목록 — 개요 화면에 들어가는 3줄짜리.
 * 출처: 아카이브/app.js .attention-list
 *
 * @param {{rows: [string, string, string, number, string][]}} props
 *   [국기, 국명, 횟수, 막대 %, 증감]
 */
export function AttentionList({ rows, limit = 3 }) {
  return (
    <div className={s.attentionList}>
      {rows.slice(0, limit).map((r) => (
        <div className={s.attentionRow} key={r[1]}>
          <span className={s.flag}>{r[0]}</span>
          <div>
            <strong>{r[1]}</strong>
            <div className={s.bar}>
              <i style={{ width: `${r[3]}%` }} />
            </div>
          </div>
          <span>{r[2]}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * 국가 관심도 전체 — 방향 전환(보낸/받은) + 요약 인사이트 + 순위 목록.
 * 관심도를 절대 기사 수가 아니라 방향으로 나눠 보여주는 것이 이 화면의 요지다.
 * 출처: 아카이브/app.js countryAttentionMarkup()
 *
 * @param {{country: string, direction: 'outgoing'|'incoming',
 *          onDirection?: (d: string) => void,
 *          rows: [string, string, string, number, string][]}} props
 */
export default function AttentionPanel({ country, flag = '🌐', direction, onDirection, rows }) {
  const outgoing = direction === 'outgoing';
  return (
    <>
      <div className={s.directionSwitch} role="group" aria-label="관심 방향">
        <button
          type="button"
          className={outgoing ? s.on : ''}
          aria-pressed={outgoing}
          onClick={() => onDirection?.('outgoing')}
        >
          언급한 국가
        </button>
        <button
          type="button"
          className={!outgoing ? s.on : ''}
          aria-pressed={!outgoing}
          onClick={() => onDirection?.('incoming')}
        >
          언급받은 국가
        </button>
      </div>

      <div className={s.attentionInsight}>
        <span className={s.attentionNode}>{outgoing ? flag : rows[0]?.[0] || '🌐'}</span>
        <i className={s.attentionArrow} />
        <span className={s.attentionNode}>{outgoing ? rows[0]?.[0] || '🌐' : flag}</span>
        <div>
          <small>{outgoing ? `${country} → 해외` : `해외 → ${country}`}</small>
          <strong>
            {rows.length ? (outgoing ? `${rows[0][1]}에 대한 언급이 가장 많아요` : `${rows[0][1]}에서 가장 많이 언급했어요`) : '국가 언급 데이터가 없습니다.'}
          </strong>
          {rows.length > 0 && <p>전체 국가 언급 중 {rows[0][2]}를 차지합니다.</p>}
        </div>
      </div>

      <SectionTitle
        title={outgoing ? `${country}이 언급한 국가` : `${country}을 언급한 국가`}
        note="기사 내 국가명 언급 기준"
      />

      <div className={s.rankList}>
        {rows.map((row, index) => (
          <div className={s.rankRow} key={row[1]}>
            <span className={s.rankNum}>{String(index + 1).padStart(2, '0')}</span>
            <span className={s.flag}>{row[0]}</span>
            <div>
              <strong>{row[1]}</strong>
              <span className={s.bar}>
                <i style={{ width: `${row[3]}%` }} />
              </span>
            </div>
            <span className={s.count}>
              {row[2]}
              <b className={row[4].startsWith('-') ? s.down : ''}>{row[4]}</b>
            </span>
          </div>
        ))}
      </div>

    </>
  );
}
