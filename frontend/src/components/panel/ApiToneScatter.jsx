import { P, sg, toneVar } from '../../lib/tone.js';
import { flagOf, scoreOf, fmt } from '../../data/responseAdapters.js';
import s from './panel.module.css';

const sdOf = (value) => value == null ? null : Number(value) / 50;
const deviationLabel = (sd) => sd < 0.2 ? '낮음' : sd < 0.4 ? '보통' : '높음';

export default function ApiToneScatter({ rows = [], spot, onSelectCountry }) {
  if (!rows.length) return <p role="status">최근 24시간 논조 데이터가 없습니다.</p>;
  return <div className={s.toneBlock}>
    <div className={s.toneAxis}><span>부정 −1.0</span><span>중립 0</span><span>긍정 +1.0</span></div>
    <div className={s.toneRows}>{rows.map((row) => {
      const id = row.country.countryCode.toLowerCase();
      const enough = row.articleCount !== 1;
      const score = scoreOf(row.toneAvg);
      const scorePosition = P(score);
      const rangeStart = P(scoreOf(row.toneMin));
      const rangeEnd = P(scoreOf(row.toneMax));
      const sd = sdOf(row.toneSd);
      const canShowDeviation = row.articleCount == null ? sd != null : row.articleCount >= 2 && sd != null;
      return <button key={id} type="button" className={`${s.toneRow} ${spot === id ? s.toneRowSpot : ''}`}
        onClick={() => onSelectCountry(id)} aria-pressed={spot === id}>
        <span className={s.flag}>{flagOf(id)}</span><span className={s.toneName}>{row.country.countryName}</span>
        <span className={s.toneN}>{row.articleCount == null ? '표본 수 미제공' : `${fmt(row.articleCount)}건`}</span>
        <span className={s.toneTrack} title={score == null ? undefined : `최소 ${sg(scoreOf(row.toneMin))} / 평균 ${sg(score)} / 최대 ${sg(scoreOf(row.toneMax))}`}>{score !== null && <>
          <i className={s.toneRange} style={{ left: `${rangeStart}%`, width: `${Math.max(0, rangeEnd - rangeStart)}%`, background: toneVar(score) }} />
          <i className={s.toneFill} style={{ left: `${Math.min(50, scorePosition)}%`, width: `${Math.abs(scorePosition - 50)}%`, background: toneVar(score) }} />
        </>}</span>
        <span className={s.toneBadge} style={{ color: score == null || !enough ? 'var(--wtw-nodata)' : toneVar(score) }}>
          {!enough ? '표본 부족' : score === null ? '분석 없음' : sg(score)}
        </span>
        <span className={s.toneWord} title={canShowDeviation ? `논조 표준편차 ${sd.toFixed(2)}` : '기사 1건으로는 논조 편차를 산출할 수 없습니다.'}>
          {!canShowDeviation ? '편차 산출 불가' : `σ ${sd.toFixed(2)} · ${row.articleCount == null || row.articleCount >= 30 ? deviationLabel(sd) : '참고용'}`}
        </span>
      </button>;
    })}</div>
    <details className={s.method}>
      <summary>논조 해석 기준</summary>
      <p>색 막대는 중립점에서 국가별 평균 논조 방향으로 뻗고, 옅은 띠는 최소~최대 논조입니다.
      σ는 기사별 논조의 표준편차이며 클수록 논조가 다양합니다. 원점수와 표준편차는 −1~1 척도에 맞게
      환산했습니다. 기사 1건은 편차를 산출할 수 없고, 2~29건의 편차는 참고용으로 표시합니다.
      평균 논조 숫자는 기사 1건일 때만 표본 부족으로 표시합니다.</p>
    </details>
  </div>;
}
