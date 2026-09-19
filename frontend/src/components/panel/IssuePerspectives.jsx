import { useState } from 'react';
import { api } from '../../data/api.js';
import { useResource } from '../../data/useResource.js';
import { articleCard, fmt, flagOf, scoreOf } from '../../data/responseAdapters.js';
import { flagImageOf } from '../../data/countries.js';
import { issueMetrics, issueCountryPerspectives, issueToneDeviation } from '../../data/issuePerspective.js';
import { P, toneLabel3, sg } from '../../lib/tone.js';
import { SectionTitle, SubHeading } from './PanelChrome.jsx';
import ArticleFeed from './ArticleFeed.jsx';
import { InterestButton } from '../../personalization/Personalization.jsx';
import s from './issuePerspectives.module.css';

export default function IssuePerspectives({ data, issueId, asOf, countryAnalyses, analysis, spot, onSelectCountry }) {
  const [expandedIssueId, setExpandedIssueId] = useState(null);
  const showAllCountries = expandedIssueId === issueId;
  const ranked = issueCountryPerspectives(data, countryAnalyses.data?.countryAnalyses);
  const visibleCountries = showAllCountries ? ranked : ranked.slice(0, 10);
  const metrics = issueMetrics(ranked);
  const deviation = issueToneDeviation(ranked);
  const scoredRows = ranked.filter((row) => row.toneAvg != null && Number.isFinite(Number(row.toneAvg)));
  const hasBounds = scoredRows.length > 0 && scoredRows.every((row) => row.toneMin != null && row.toneMax != null
    && Number.isFinite(Number(row.toneMin)) && Number.isFinite(Number(row.toneMax)));
  const minimum = hasBounds ? scoreOf(Math.min(...scoredRows.map((row) => Number(row.toneMin)))) : null;
  const maximum = hasBounds ? scoreOf(Math.max(...scoredRows.map((row) => Number(row.toneMax)))) : null;
  const spreadStart = deviation == null || metrics.score == null ? null : Math.max(-1, metrics.score - deviation);
  const spreadEnd = deviation == null || metrics.score == null ? null : Math.min(1, metrics.score + deviation);
  const overallToneClass = metrics.score == null ? s.toneUnknown : metrics.score > 0.32 ? s.tonePositive : metrics.score <= -0.34 ? s.toneNegative : s.toneNeutral;
  const selected = ranked.find((row) => row.country.countryCode.toLowerCase() === spot);
  const articles = useResource(selected ? `issue-evidence:${asOf}:${issueId}:${spot}` : null,
    (signal) => api.overview(issueId, selected.country.countryCode, signal, asOf));
  return <section className={s.screen}>
    <div className={s.eyebrow}><span>주요 이슈</span><span>{asOf ? '선택 시점' : '현재 시점'}</span></div>
    <div className={s.headingRow}>
      <SubHeading title={data.issuePreview.issueTitle} desc={data.issuePreview.themeTitle} />
      <InterestButton kind="issues" id={issueId} name={data.issuePreview.issueTitle} />
    </div>
    <div className={s.metrics}>
      <div className={s.metricCard}><span className={s.metricLabel}>관련 기사</span><strong>{fmt(metrics.articleCount)}<em>건</em></strong></div>
      <div className={s.metricCard}><span className={s.metricLabel}>보도 국가</span><strong>{fmt(metrics.countryCount)}<em>개국</em></strong></div>
      <div className={`${s.metricCard} ${s.overallCard} ${overallToneClass}`}>
        <span className={s.metricLabel}>관련 보도 평균 논조
          <span className={s.helpWrap} aria-label="논조 그래프 해석 안내">
            <span className={s.helpIcon} aria-hidden="true">!</span>
            <span className={s.helpTooltip} role="tooltip">선은 기사 논조의 최소~최대 범위, 점은 평균입니다. 음영은 평균을 중심으로 한 표준편차 범위이며 넓을수록 기사별 관점 차이가 큽니다.</span>
          </span>
        </span>
        <strong className={s.overallTone}>{metrics.score == null ? '분석 없음' : toneLabel3(metrics.score)}</strong>
        <div className={s.overallChart} role="img" aria-label={`평균 ${metrics.score == null ? '없음' : sg(metrics.score)}, 최소 ${minimum == null ? '없음' : sg(minimum)}, 최대 ${maximum == null ? '없음' : sg(maximum)}, 표준편차 ${deviation == null ? '산출 불가' : deviation.toFixed(2)}`}>
          <div className={s.toneAxis}><span>부정 −1</span><span>중립 0</span><span>긍정 +1</span></div>
          <div className={s.overallTrack}>
            {spreadStart != null && <span className={s.deviationBand} style={{ left: `${P(spreadStart)}%`, width: `${P(spreadEnd) - P(spreadStart)}%` }} />}
            <span className={s.toneZero} />
            {hasBounds && <span className={s.toneRange} style={{ left: `${P(minimum)}%`, width: `${P(maximum) - P(minimum)}%` }} />}
            {metrics.score != null && <span className={s.toneMean} style={{ left: `${P(metrics.score)}%` }} />}
          </div>
          <div className={s.toneValues}><span>최소 {minimum == null ? '없음' : sg(minimum)}</span><span>평균 {metrics.score == null ? '없음' : sg(metrics.score)}</span><span>최대 {maximum == null ? '없음' : sg(maximum)}</span></div>
        </div>
      </div>
    </div>
    <SectionTitle title="국가별 언론의 보도 관점" note={`보도량 순 · ${ranked.length}개국`}
      help="언론사 소재 국가 기준입니다. 정부 입장이나 국민 여론을 뜻하지 않습니다. 평균 논조는 국가별 기사 수로 가중한 값입니다(−1 ~ +1)." />
    {countryAnalyses.loading && !countryAnalyses.data && <p className={s.hint} role="status">국가별 분석 요약을 불러오고 있습니다…</p>}
    {countryAnalyses.error && <div role="alert"><p>국가별 분석 요약을 불러오지 못했습니다.</p>
      <button type="button" onClick={countryAnalyses.retry}>분석 요약 다시 시도</button></div>}
    <div className={s.list}>
      {visibleCountries.map((row, index) => {
        const code = row.country.countryCode.toLowerCase();
        const score = scoreOf(row.toneAvg);
        const min = scoreOf(row.toneMin);
        const max = scoreOf(row.toneMax);
        const sd = row.toneSd == null ? null : Number(row.toneSd) / 50;
        const hasScore = score != null && Number.isFinite(score);
        const hasRange = min != null && max != null && Number.isFinite(min) && Number.isFinite(max);
        const toneClass = !hasScore ? s.toneUnknown : score > 0.32 ? s.tonePositive : score <= -0.34 ? s.toneNegative : s.toneNeutral;
        return <button type="button" key={code} className={`${s.row} ${spot === code ? s.selected : ''}`}
          aria-pressed={spot === code} onClick={() => onSelectCountry(code)}>
          <span className={s.rank}>{index + 1}</span><span className={s.flag} aria-hidden="true">
            <img src={flagImageOf(code)} alt="" onError={(event) => { event.currentTarget.hidden = true; event.currentTarget.nextElementSibling.hidden = false; }} />
            <span hidden>{flagOf(code)}</span>
          </span>
          <span className={s.identity}><strong>{row.country.countryName}</strong>
            <span className={`${s.toneBadgeWrap} ${toneClass}`}>
              <span className={s.toneBadge}>{hasScore ? toneLabel3(score) : '분석 없음'}</span>
              <span className={s.tonePopover} role="tooltip">
                <strong>{row.country.countryName} 평균 논조 {hasScore ? sg(score) : '분석 없음'}</strong>
                <span className={s.toneAxis}><span>부정 −1</span><span>중립 0</span><span>긍정 +1</span></span>
                <span className={s.toneTrack}>
                  <span className={s.toneZero} />
                  {hasRange && <span className={s.toneRange} style={{ left: `${P(min)}%`, width: `${Math.max(0, P(max) - P(min))}%` }} />}
                  {hasScore && <span className={s.toneMean} style={{ left: `${P(score)}%` }} />}
                </span>
                <span className={s.toneValues}><span>최소 {min != null && Number.isFinite(min) ? sg(min) : '없음'}</span><span>최대 {max != null && Number.isFinite(max) ? sg(max) : '없음'}</span></span>
                <span className={s.toneDeviation}>표준편차 σ {sd != null && Number.isFinite(sd) && (row.articleCount == null || row.articleCount >= 2) ? sd.toFixed(2) : '산출 불가'}</span>
                <span className={s.toneHelp}>선: 최소~최대 · 점: 평균 · −1~1 기준</span>
              </span>
            </span></span>
          <span className={s.summary}>{row.analysis?.title || '보도 관점 요약'}<small>{row.analysis?.summary
            || (countryAnalyses.loading ? '분석 요약을 불러오는 중…' : countryAnalyses.error ? '분석 요약 조회 실패' : '등록된 분석 없음')}</small></span>
          <span className={s.count}>{fmt(row.articleCount)}건<small>관련 기사</small></span>
        </button>;
      })}
      {!ranked.length && <p role="status">최근 24시간 관련 기사가 있는 국가가 없습니다.</p>}
    </div>
    {ranked.length > 10 && <button type="button" className={s.moreCountries}
      onClick={() => setExpandedIssueId(showAllCountries ? null : issueId)} aria-expanded={showAllCountries}>
      {showAllCountries ? '접기' : `더보기 · ${ranked.length - 10}개국`}
    </button>}
    {!selected && <p className={s.hint}>{spot ? '선택한 국가의 최근 24시간 관련 기사가 없습니다.' : '국가를 선택하면 보도 관점의 상세 요약과 대표 기사를 확인할 수 있습니다.'}</p>}
    {selected && <section className={s.evidence}>
      <SectionTitle title={`${selected.country.countryName} 언론의 보도 관점`} />
      {analysis.loading && !analysis.data ? <p role="status">보도 관점을 불러오고 있습니다…</p>
        : analysis.error ? <div role="alert"><p>분석 결과를 불러오지 못했습니다.</p>
          <button type="button" onClick={analysis.retry}>분석 상세 다시 시도</button></div>
          : analysis.data ? <div className={s.analysis}>
            <h3>{analysis.data.title}</h3>
            <p>{analysis.data.summary}</p>
            {analysis.data.details?.length > 0 && <ul>{analysis.data.details.map((detail, index) => <li key={index}>{detail}</li>)}</ul>}
            <small>분석에 사용한 기사 {fmt(analysis.data.articleCount)}건
              {analysis.data.windowEnd && <> · 분석 기준 시각 <time dateTime={analysis.data.windowEnd}>
                {new Date(analysis.data.windowEnd).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
              </time> (한국 시간)</>}</small>
          </div> : <p className={s.hint} role="status">조회 시점까지 등록된 국가별 분석이 없습니다.</p>}
      <SectionTitle title={`${selected.country.countryName} 대표 기사`} note="조회 시점까지 전체 기간 · 관련도순 최대 10건" />
      <p className={s.hint}>관련도순 대표 기사이며, 요약 분석에 사용한 기사 목록과는 다를 수 있습니다.</p>
      {articles.loading && !articles.data ? <p role="status">기사를 불러오고 있습니다…</p>
        : articles.error ? <div role="alert"><p>{articles.error.message}</p><button type="button" onClick={articles.retry}>다시 시도</button></div>
          : articles.data?.representArticles?.length ? <ArticleFeed articles={articles.data.representArticles.map(articleCard)} />
            : <p role="status">표시할 대표 기사가 없습니다.</p>}
    </section>}
  </section>;
}
