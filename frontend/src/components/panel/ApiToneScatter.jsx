import { P, sg, toneVar } from '../../lib/tone.js';
import { flagOf, scoreOf, fmt } from '../../data/responseAdapters.js';
import s from './panel.module.css';

const sdOf = (value) => value == null ? null : Number(value) / 50;
const deviationLabel = (sd) => sd < 0.2 ? '낮음' : sd < 0.4 ? '보통' : '높음';

export default function ApiToneScatter({ rows = [], spot, onSelectCountry }) {
  if (!rows.length) return <p role="status">최근 24시간 논조 데이터가 없습니다.</p>;
  return <div className={s.toneBlock}>
    <div className={s.toneAxis}><span>부정 −1.0</span><span>중립 0</span><span>긍정 +1.0</span></div>
    <span className={s.spark}>
      <i className={s.sparkRule} /><i className={s.sparkMid} />
      {rows.filter((row) => row.toneAvg != null).map((row) => {
        const id = row.country.countryCode.toLowerCase();
        const average = scoreOf(row.toneAvg);
        const min = scoreOf(row.toneMin);
        const max = scoreOf(row.toneMax);
        const lowSample = row.articleCount != null && row.articleCount < 30;
        const title = `${row.country.countryName} · 최소 ${sg(min)} / 평균 ${sg(average)} / 최대 ${sg(max)}${lowSample ? ` · 표본 ${row.articleCount}건` : ''}`;
        return <span key={id} className={`${s.sparkCountry} ${lowSample ? s.sparkLowSample : ''}`}>
          <i className={s.sparkRange} style={{ left: `${P(min)}%`, width: `${Math.max(0, P(max) - P(min))}%` }} title={title} />
          <i className={`${s.sparkDot} ${spot === id ? s.sparkMe : ''}`}
            style={{ left: `${P(average)}%`, background: toneVar(average) }} title={title} />
        </span>;
      })}
    </span>
    <div className={s.toneRows}>{rows.map((row) => {
      const id = row.country.countryCode.toLowerCase();
      const enough = row.articleCount == null || row.articleCount >= 30;
      const score = scoreOf(row.toneAvg);
      const sd = sdOf(row.toneSd);
      const canShowDeviation = row.articleCount == null ? sd != null : row.articleCount >= 2 && sd != null;
      return <button key={id} type="button" className={`${s.toneRow} ${spot === id ? s.toneRowSpot : ''}`}
        onClick={() => onSelectCountry(id)} aria-pressed={spot === id}>
        <span className={s.flag}>{flagOf(id)}</span><span className={s.toneName}>{row.country.countryName}</span>
        <span className={s.toneN}>{row.articleCount == null ? '표본 수 미제공' : `${fmt(row.articleCount)}건`}</span>
        <span className={s.toneTrack} title={score == null ? undefined : `최소 ${sg(scoreOf(row.toneMin))} / 평균 ${sg(score)} / 최대 ${sg(scoreOf(row.toneMax))}`}>{score !== null && <>
          <i style={{ position: 'absolute', left: `${P(scoreOf(row.toneMin))}%`, width: `${Math.max(0, P(scoreOf(row.toneMax)) - P(scoreOf(row.toneMin)))}%`, height: 4, top: '50%', background: toneVar(score), opacity: .3 }} />
          <i className={s.toneMark} style={{ left: `${P(score)}%`, background: toneVar(score) }} />
        </>}</span>
        <span className={s.toneBadge} style={{ color: score == null || !enough ? 'var(--wtw-nodata)' : toneVar(score) }}>
          {!enough ? '표본 부족' : score === null ? '분석 없음' : sg(score)}
        </span>
        <span className={s.toneWord} title={canShowDeviation ? `논조 표준편차 ${sd.toFixed(2)}` : '기사 1건으로는 논조 편차를 산출할 수 없습니다.'}>
          {!canShowDeviation ? '편차 산출 불가' : `σ ${sd.toFixed(2)} · ${enough ? deviationLabel(sd) : '참고용'}`}
        </span>
      </button>;
    })}</div>
    <p className={s.method}>최근 24시간 발행 기사 기준입니다. 점은 국가별 평균, 가로선은 최소~최대 논조입니다.
      표본 30건 미만인 국가의 점과 선은 흐리게 표시합니다.
      σ는 기사별 논조의 표준편차이며 클수록 논조가 다양합니다. 원점수와 표준편차는 −1~1 척도에 맞게
      환산했습니다. 기사 1건은 편차를 산출할 수 없고, 2~29건의 편차는 참고용으로 표시합니다.
      평균 논조는 30건 미만일 때 숨깁니다.</p>
  </div>;
}
