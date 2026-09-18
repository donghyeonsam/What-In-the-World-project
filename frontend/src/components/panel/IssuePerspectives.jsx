import { api } from '../../data/api.js';
import { useResource } from '../../data/useResource.js';
import { articleCard, fmt, flagOf, scoreOf } from '../../data/responseAdapters.js';
import { issueMetrics, rankIssueCountries } from '../../data/issuePerspective.js';
import { toneLabel3, toneVar, sg } from '../../lib/tone.js';
import { KpiCards, SectionTitle, PolicyNote, SubHeading } from './PanelChrome.jsx';
import ArticleFeed from './ArticleFeed.jsx';
import { InterestButton } from '../../personalization/Personalization.jsx';
import s from './issuePerspectives.module.css';

export default function IssuePerspectives({ data, issueId, asOf, spot, onSelectCountry }) {
  const ranked = rankIssueCountries(data.countryTones);
  const metrics = issueMetrics(ranked);
  const selected = ranked.find((row) => row.country.countryCode.toLowerCase() === spot);
  const articles = useResource(selected ? `issue-evidence:${asOf}:${issueId}:${spot}` : null,
    (signal) => api.overview(issueId, selected.country.countryCode, signal, asOf));
  return <section className={s.screen}>
    <div className={s.eyebrow}><span>주요 이슈</span><span>{asOf ? '선택 시점' : '현재 시점'} 직전 24시간</span></div>
    <SubHeading title={data.issuePreview.issueTitle} desc={data.issuePreview.themeTitle} />
    <InterestButton kind="issues" id={issueId} name={data.issuePreview.issueTitle} />
    <div className={s.metrics}><KpiCards items={[
      { label: '관련 기사 · 최근 24시간', value: fmt(metrics.articleCount), unit: '건' },
      { label: '보도 국가 · 최근 24시간', value: fmt(metrics.countryCount), unit: '개국' },
      { label: '관련 보도 평균 논조', value: metrics.score == null ? '분석 없음' : sg(metrics.score) },
    ]} /></div>
    <PolicyNote>언론사 소재 국가 기준입니다. 정부 입장이나 국민 여론을 뜻하지 않습니다. 평균 논조는 국가별 기사 수로 가중한 값입니다(−1 ~ +1).</PolicyNote>
    <SectionTitle title="국가별 언론의 보도 관점" note={`보도량 순 · 상위 ${Math.min(10, ranked.length)}개국`} />
    <div className={s.list}>
      {ranked.slice(0, 10).map((row, index) => {
        const code = row.country.countryCode.toLowerCase();
        const score = scoreOf(row.toneAvg);
        return <button type="button" key={code} className={`${s.row} ${spot === code ? s.selected : ''}`}
          aria-pressed={spot === code} onClick={() => onSelectCountry(code)}>
          <span className={s.rank}>{index + 1}</span><span className={s.flag}>{flagOf(code)}</span>
          <span className={s.identity}><strong>{row.country.countryName}</strong>
            <small style={{ color: score == null ? undefined : toneVar(score) }}>{score == null ? '논조 분석 없음' : `${toneLabel3(score)} ${sg(score)}`}</small></span>
          <span className={s.summary}>보도 관점 요약<small>데이터 추가 필요</small></span>
          <span className={s.count}>{fmt(row.articleCount)}건<small>관련 기사</small></span>
        </button>;
      })}
      {!ranked.length && <p role="status">최근 24시간 관련 기사가 있는 국가가 없습니다.</p>}
    </div>
    <div className={s.missing}>이슈 발생국 · 데이터 추가 필요<span>발생국 정보가 없어 국가 간 연결선은 표시하지 않습니다.</span></div>
    {!selected && <p className={s.hint}>{spot ? '선택한 국가의 최근 24시간 관련 기사가 없습니다.' : '국가를 선택하면 해당 국가의 대표 기사를 확인할 수 있습니다.'}</p>}
    {selected && <section className={s.evidence}>
      <SectionTitle title={`${selected.country.countryName} 대표 기사`} note="조회 시점까지 전체 기간 · 관련도순 최대 10건" />
      <p className={s.hint}>보도 관점 요약 · 데이터 추가 필요. 아래 기사에서 실제 보도 내용을 확인할 수 있습니다.</p>
      {articles.loading && !articles.data ? <p role="status">기사를 불러오고 있습니다…</p>
        : articles.error ? <div role="alert"><p>{articles.error.message}</p><button type="button" onClick={articles.retry}>다시 시도</button></div>
          : articles.data?.representArticles?.length ? <ArticleFeed articles={articles.data.representArticles.map(articleCard)} />
            : <p role="status">표시할 대표 기사가 없습니다.</p>}
    </section>}
  </section>;
}
