import { P, sg, toneVar } from '../../lib/tone.js';
import { flagOf, scoreOf, fmt } from '../../data/responseAdapters.js';
import s from './panel.module.css';

export default function ApiToneScatter({ rows = [], spot, onSelectCountry }) {
  if (!rows.length) return <p role="status">최근 24시간 논조 데이터가 없습니다.</p>;
  return <div className={s.toneBlock}>
    <div className={s.toneAxis}><span>부정 −1.0</span><span>중립 0</span><span>긍정 +1.0</span></div>
    <span className={s.spark}>
      <i className={s.sparkRule} /><i className={s.sparkMid} />
      {rows.filter((row) => row.toneAvg != null && (row.articleCount == null || row.articleCount >= 30)).map((row) =>
        <i key={row.country.countryCode} className={`${s.sparkDot} ${spot === row.country.countryCode.toLowerCase() ? s.sparkMe : ''}`}
          style={{ left: `${P(scoreOf(row.toneAvg))}%`, background: toneVar(scoreOf(row.toneAvg)) }}
          title={`${row.country.countryName} 평균 ${sg(scoreOf(row.toneAvg))}`} />)}
    </span>
    <div className={s.toneRows}>{rows.map((row) => {
      const id = row.country.countryCode.toLowerCase();
      const enough = row.articleCount == null || row.articleCount >= 30;
      const score = scoreOf(row.toneAvg);
      return <button key={id} type="button" className={`${s.toneRow} ${spot === id ? s.toneRowSpot : ''}`}
        onClick={() => onSelectCountry(id)} aria-pressed={spot === id}>
        <span className={s.flag}>{flagOf(id)}</span><span className={s.toneName}>{row.country.countryName}</span>
        <span className={s.toneN}>{row.articleCount == null ? '표본 수 미제공' : `${fmt(row.articleCount)}건`}</span>
        <span className={s.toneTrack}>{enough && score !== null && <>
          <i style={{ position: 'absolute', left: `${P(scoreOf(row.toneMin))}%`, width: `${Math.max(0, P(scoreOf(row.toneMax)) - P(scoreOf(row.toneMin)))}%`, height: 4, top: '50%', background: toneVar(score), opacity: .3 }} />
          <i className={s.toneMark} style={{ left: `${P(score)}%`, background: toneVar(score) }} />
        </>}</span>
        <span className={s.toneBadge} style={{ color: score == null || !enough ? 'var(--wtw-nodata)' : toneVar(score) }}>
          {!enough ? '표본 부족' : score === null ? '분석 없음' : sg(score)}
        </span>
      </button>;
    })}</div>
    <p className={s.method}>최근 24시간 발행 기사 기준입니다. 점은 국가별 평균, 선은 최소~최대 논조입니다.
      원점수 0~100을 −1~1로 환산했습니다. 표본 수가 제공된 경우 30건 미만은 숨깁니다.</p>
  </div>;
}
