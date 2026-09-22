import { fmt } from '../../data/responseAdapters.js';
import s from './panel.module.css';

export default function IssueCountryAnalysis({ countryName, toneColor, resource, onClose }) {
  const { data, loading, error, retry } = resource;
  return <section className={`${s.countryAnalysis} ${toneColor ? s.countryAnalysisTinted : ''}`}
    style={toneColor ? { '--analysis-tone-rgb': toneColor } : undefined}
    aria-label={`${countryName} 매체의 보도 관점`}>
    <div className={s.countryAnalysisHeading}>
      <strong>{countryName} · 보도 관점</strong>
      {onClose && <button type="button" onClick={onClose} aria-label="국가 분석 닫기">닫기</button>}
    </div>
    {loading && !data ? <p role="status">보도 관점을 불러오고 있습니다…</p>
      : error ? <div role="alert"><p>분석 결과를 불러오지 못했습니다.</p><button type="button" onClick={retry}>다시 시도</button></div>
        : !data ? <p role="status">조회 시점까지 등록된 국가별 분석이 없습니다.</p>
          : <>
            <div className={s.countryAnalysisMeta}>
              <small>분석에 사용한 기사 {fmt(data.articleCount)}건</small>
            </div>
            <h4>{data.title}</h4>
            <p className={s.countryAnalysisSummary}>{data.summary}</p>
            {data.details?.length > 0 && <ul>{data.details.map((detail, index) => <li key={index}>{detail}</li>)}</ul>}
            {data.windowEnd && <p className={s.countryAnalysisFoot}>분석 기준 시각 · <time dateTime={data.windowEnd}>
              {new Date(data.windowEnd).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
            </time> (한국 시간)</p>}
          </>}
  </section>;
}
