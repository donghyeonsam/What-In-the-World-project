import { P, sg, toneVar, toneLabel5 } from '../../lib/tone.js';
import { C, C_NAME, MIN_SAMPLE, hasSample, spreadOf, baseOf } from '../../data/model.js';
import { josaRo } from '../../lib/format.js';
import s from './panel.module.css';

/**
 * 국가별 논조 산포 — 이 통합안에서 논조를 보여주는 유일한 방식이다.
 *
 * 세 시안의 조각을 하나로 합쳤다.
 *   · 신문   — 한 축 위에 나라별 점을 흩뿌린다. 평균을 내지 않는다.
 *   · 코스모스 — 표본이 MIN_SAMPLE 미만이면 값을 감추고 '표본 부족'으로 적는다.
 *   · 신문   — 매체가 적어 편차가 좁은 나라는 따로 경고한다.
 *
 * 왜 평균이 아닌가: 국가 평균은 그 나라 내부의 분열을 지우고
 * "이 나라는 이렇게 생각한다"는 결론을 만든다. 여기서는 결론 대신 분포를 준다.
 *
 * @param {{issue: object, scope?: string|null, spot?: string|null,
 *          onSelectCountry?: (id: string) => void, showMethod?: boolean}} props
 *   scope  이 국가 코드의 점만 크게, 나머지는 흐리게 그린다
 *   spot   지구본이 지금 바라보는 나라 — 그 줄에 표시만 한다
 *
 * 줄을 누르면 화면이 바뀌지 않는다. 지구본만 그 나라로 돈다(같은 줄을 다시 누르면 해제).
 * 논조를 읽다가 "그게 어디였지"를 확인하는 동작이라, 보던 이슈를 빼앗을 이유가 없다.
 */
export default function ToneScatter({
  issue,
  scope = null,
  spot = null,
  onSelectCountry,
  showMethod = true,
}) {
  const rows = Object.entries(issue.tone)
    .map(([cid, d]) => ({ cid, d }))
    .sort((a, b) => b.d.n - a.d.n);

  const reliable = rows.filter((r) => hasSample(r.d));
  const values = reliable.map((r) => r.d.s);
  const spread = values.length ? Math.max(...values) - Math.min(...values) : 0;

  /* 매체가 적어 편차가 좁은 나라 — 국가가 아니라 소수 매체의 논조일 수 있다 */
  const narrow = reliable
    .filter((r) => spreadOf(issue.id, r.cid) < 0.1)
    .map((r) => `${C_NAME(r.cid)}(매체 ${C(r.cid).m}곳)`);

  return (
    <div className={s.toneBlock}>
      <div className={s.toneAxis}>
        <span>비판 −1.0</span>
        <span>중립 0</span>
        <span>우호 +1.0</span>
      </div>

      {/* 산포 — 표본이 충분한 나라만 점을 찍는다 */}
      <span className={s.spark}>
        <i className={s.sparkRule} />
        <i className={s.sparkMid} />
        {reliable.map(({ cid, d }) => (
          <i
            key={cid}
            className={`${s.sparkDot} ${scope === cid ? s.sparkMe : ''}`}
            style={{
              left: `${P(d.s)}%`,
              background: toneVar(d.s),
              opacity: scope ? (scope === cid ? 1 : 0.32) : 0.66,
            }}
            title={`${C_NAME(cid)} ${sg(d.s)}`}
          />
        ))}
      </span>

      <div className={s.toneSummary}>
        <span>
          보도한 나라 <b>{rows.length}</b>
        </span>
        <span>
          값을 쓸 수 있는 나라 <b>{reliable.length}</b>
        </span>
        <span>
          논조 분열도 <b>{spread.toFixed(2)}</b>
        </span>
        <span>
          평시 대비 <b>{sg(issue.momentum)}</b>
        </span>
      </div>

      {narrow.length > 0 && (
        <div className={s.warn}>
          <b>매체 간 편차 경고</b>
          {narrow.join(', ')}은 수집된 매체 사이의 논조 편차가 좁습니다. “그 나라의 논조”가 아니라
          “수집 가능한 소수 매체의 논조”일 수 있습니다.
        </div>
      )}

      <div className={s.toneRows}>
        {rows.map(({ cid, d }) => {
          const ok = hasSample(d);
          const base = baseOf(issue.id, cid);
          const Row = onSelectCountry ? 'button' : 'div';
          const spotted = spot === cid; /* 지구본이 지금 이 나라를 보고 있다 */
          return (
            <Row
              key={cid}
              type={onSelectCountry ? 'button' : undefined}
              className={`${s.toneRow} ${scope === cid ? s.toneRowOn : ''} ${
                spotted ? s.toneRowSpot : ''
              }`}
              onClick={onSelectCountry ? () => onSelectCountry(cid) : undefined}
              aria-pressed={onSelectCountry ? spotted : undefined}
              title={
                onSelectCountry
                  ? spotted
                    ? '지구본 시점 되돌리기'
                    : `지구본을 ${josaRo(C_NAME(cid))} 돌리기`
                  : undefined
              }
            >
              <span className={s.flag}>{C(cid).flag}</span>
              <span className={s.toneName}>{C_NAME(cid)}</span>
              <span className={s.toneN}>{d.n}건</span>
              {ok ? (
                <span className={s.toneTrack}>
                  <i className={s.toneBase} style={{ left: `${P(base)}%` }} />
                  <i className={s.toneMark} style={{ left: `${P(d.s)}%`, background: toneVar(d.s) }} />
                </span>
              ) : (
                <span className={s.toneTrackOff} />
              )}
              <span
                className={s.toneBadge}
                style={
                  ok
                    ? { color: toneVar(d.s), borderColor: 'currentColor' }
                    : { color: 'var(--wtw-nodata)', borderColor: 'currentColor' }
                }
              >
                {ok ? sg(d.s) : '표본 부족'}
              </span>
              <span className={s.toneWord}>{ok ? toneLabel5(d.s) : `${MIN_SAMPLE}건 미만`}</span>
              {spotted && <i className={s.spotMark} aria-hidden="true" />}
            </Row>
          );
        })}
      </div>

      {showMethod && (
        <p className={s.method}>
          <b>읽는 법.</b> 굵은 점이 오늘 논조, 얇은 세로선이 그 나라의 최근 30일 평시 기준선입니다.
          표본이 {MIN_SAMPLE}건에 못 미치는 나라는 값을 적지 않습니다 — 숫자를 못 믿을 때는
          숫자를 지우는 편이 정직합니다. <b>평균을 쓰지 않는 이유.</b> 국가 평균은 그 나라 내부의
          분열을 지우고 “이 나라는 이렇게 생각한다”는 결론을 만듭니다.
        </p>
      )}
    </div>
  );
}

/** 목록 안에 한 줄로 들어가는 축소판 — 이슈 카드 옆 등 */
export function ToneSparkMini({ tone, scope = null }) {
  const rows = Object.entries(tone).filter(([, d]) => hasSample(d));
  return (
    <span className={`${s.spark} ${s.sparkMini}`}>
      <i className={s.sparkRule} />
      <i className={s.sparkMid} />
      {rows.map(([cid, d]) => (
        <i
          key={cid}
          className={`${s.sparkDot} ${scope === cid ? s.sparkMe : ''}`}
          style={{
            left: `${P(d.s)}%`,
            background: toneVar(d.s),
            opacity: scope ? (scope === cid ? 1 : 0.3) : 0.6,
          }}
        />
      ))}
    </span>
  );
}
