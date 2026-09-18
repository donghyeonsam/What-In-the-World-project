import { fmt } from '../../data/responseAdapters.js';
import s from './panel.module.css';

export default function IssueCountryAnalysis({ countryName, noCoverage = false, toneColor, resource }) {
  const { data, loading, error, retry } = resource;
  return <section className={`${s.countryAnalysis} ${toneColor ? s.countryAnalysisTinted : ''}`}
    style={toneColor ? { '--analysis-tone-rgb': toneColor } : undefined}
    aria-label={`${countryName} 매체의 보도 관점`}>
    {loading && !data ? <p role="status">보도 관점을 불러오고 있습니다…</p>
      : error ? <div role="alert"><p>분석 결과를 불러오지 못했습니다.</p><button type="button" onClick={retry}>다시 시도</button></div>
        : !data ? <p role="status">{noCoverage
          ? `${countryName}의 최근 24시간 관련 기사가 없어 보도 관점을 표시할 수 없습니다.`
          : '보도 관점 요약 · 데이터 추가 필요.'}</p>
          : <>
            <div className={s.countryAnalysisMeta}>
              <span>보도 관점 {data.preview && <b>화면 예시</b>}</span>
              <small>{data.windowLabel} · 기사 {fmt(data.articleCount)}건</small>
            </div>
            <h4>{data.headline}</h4>
            <p className={s.countryAnalysisSummary}>{data.summary}</p>
            {data.details?.length > 0 && <ul>{data.details.slice(0, 1).map((detail, index) => <li key={index}>{detail}</li>)}</ul>}
            <p className={s.countryAnalysisFoot}>{data.preview
              ? '예시 문구입니다. 실제 기사 분석 결과는 아직 연결되지 않았습니다.'
              : data.analyzedAt ? `마지막 분석 ${new Date(data.analyzedAt).toLocaleString('ko-KR')}` : '분석 시각 정보가 없습니다.'}</p>
          </>}
  </section>;
}
