-- ============================================================================
-- witw 성능 측정용 대용량 데이터 생성기
--
-- 목적: 인덱스/플랜 튜닝의 before-after를 비교할 수 있는 재현 가능한 데이터셋.
-- 실행: psql -h localhost -U postgres -d witw -f scripts/perf/generate-bulk.sql
--       (pgAdmin 쿼리 툴에 붙여넣어도 동작 — psql 메타명령을 쓰지 않음)
--
-- ---------------------------------------------------------------------------
-- 재현성 (팀원과 숫자를 비교하려면 이 부분이 핵심)
-- ---------------------------------------------------------------------------
-- random() 을 쓰지 않습니다. random() 은 호출 순서에 의존하므로 병렬 실행이
-- 끼면 같은 setseed() 로도 다른 데이터가 나옵니다.
--
-- 대신 행 번호 g 에서 해시로 유도하는 pg_temp.prand(g, salt) 를 씁니다.
-- 실행 계획·병렬도·실행 시점과 무관하게 항상 같은 값이 나옵니다.
-- => 두 사람이 이 스크립트를 돌리면 바이트 단위로 동일한 데이터를 얻습니다.
--
-- ---------------------------------------------------------------------------
-- 데이터 특성
-- ---------------------------------------------------------------------------
-- * 국가/테마 분포가 쏠려 있습니다 (상위 4개국 약 46%, 상위 10개국 약 63%).
--   균등 분포로 만들면 모든 값의 선택도가 같아져서 플래너가 실제 운영에서 할
--   선택을 재현하지 못합니다. 인덱스 효과 측정이 무의미해집니다.
-- * published_at 은 SPREAD_HOURS(기본 72h) 에 균등 분산됩니다.
--   따라서 최근 24시간 윈도우에 약 1/3 이 걸립니다 — 24시간 필터가 얼마나
--   걸러내는지가 측정 대상이 됩니다.
-- * 약 2% 가 soft delete (deleted_at IS NOT NULL) — deleted_at 필터 경로 확인용.
-- * 약 15% 가 issue_id IS NULL — 이슈 미배정 기사.
-- * 제목/요약을 운영과 비슷한 길이로 채웁니다. 짧은 더미로 만들면 테이블이
--   작아져서 전부 shared_buffers 에 들어가고, 디스크 I/O 특성을 못 봅니다.
--
-- ---------------------------------------------------------------------------
-- 주의
-- ---------------------------------------------------------------------------
-- 맨 앞에서 아래 테이블을 TRUNCATE 합니다. 실제 수집 데이터가 있는 DB 에서
-- 절대 실행하지 마십시오. flyway_schema_history 는 건드리지 않습니다.
--
-- 생성되는 데이터는 모두 식별 가능한 접두어를 씁니다:
--   country_code : A0~D9 (숫자를 포함하므로 실제 ISO 3166-1 코드와 충돌 불가)
--   article.id   : 'perf-________'
-- ============================================================================

BEGIN;

-- 결정성 보장: 병렬 실행을 끕니다. 생성 자체는 조금 느려지지만
-- 어떤 환경에서도 동일한 결과가 나옵니다.
SET LOCAL max_parallel_workers_per_gather = 0;

-- 대량 INSERT 동안 동기 커밋을 끄면 생성 시간이 크게 줄어듭니다.
-- (측정 대상은 SELECT 이므로 생성 단계의 내구성은 중요하지 않습니다)
SET LOCAL synchronous_commit = off;


-- ----------------------------------------------------------------------------
-- 설정: 규모를 바꾸려면 이 값만 수정하십시오.
-- ----------------------------------------------------------------------------
CREATE TEMP TABLE _cfg ON COMMIT DROP AS
SELECT
    500000::bigint AS article_count,   -- 생성할 기사 수
    72::int        AS spread_hours,    -- published_at 을 뿌릴 시간 범위
    3.0::float8    AS skew_exp,        -- 쏠림 강도 (1.0=균등, 클수록 쏠림)
    40::int        AS country_count,   -- 국가 수
    68::int        AS theme_count,     -- 테마 수 (운영과 동일)
    5::int         AS field_count,     -- 분야 수 (운영과 동일)
    200::int       AS issue_count,     -- 이슈 수
    date_trunc('minute', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS anchor;


-- ----------------------------------------------------------------------------
-- 결정적 의사난수: g 와 salt 로부터 [0,1) 값을 유도합니다.
-- 같은 (g, salt) 는 언제 어디서 호출해도 같은 값을 돌려줍니다.
-- pg_temp 스키마이므로 세션 종료 시 자동으로 사라집니다.
-- ----------------------------------------------------------------------------
CREATE FUNCTION pg_temp.prand(seed bigint, salt int) RETURNS float8 AS
$$ SELECT (hashint8(seed * 1000003 + salt) & 2147483647)::float8 / 2147483647.0 $$
LANGUAGE sql IMMUTABLE;

-- 국가 인덱스(1-based) -> 코드 'A0' ~ 'D9'
CREATE FUNCTION pg_temp.ccode(idx int) RETURNS varchar(2) AS
$$ SELECT chr(65 + ((idx - 1) / 10)) || ((idx - 1) % 10)::text $$
LANGUAGE sql IMMUTABLE;


TRUNCATE article_country_mention, country_tone, article_summary,
         article, issue, theme, field, country;


-- ----------------------------------------------------------------------------
-- 기준 데이터
-- ----------------------------------------------------------------------------
INSERT INTO country (country_code, name_ko, name_en, latitude, longitude)
SELECT pg_temp.ccode(g),
       'PERF국가-' || pg_temp.ccode(g),
       'Perf Country ' || pg_temp.ccode(g),
       -60.0 + 120.0 * pg_temp.prand(g, 11),
       -180.0 + 360.0 * pg_temp.prand(g, 12)
FROM _cfg c, generate_series(1, c.country_count) g;

INSERT INTO field (id, code, name, description, created_at)
SELECT g,
       'perf_field_' || g,
       'PERF분야 ' || g,
       '성능 측정용 가상 분야 ' || g,
       c.anchor
FROM _cfg c, generate_series(1, c.field_count) g;

INSERT INTO theme (id, field_id, code, name, description, created_at, updated_at)
SELECT g,
       1 + ((g - 1) * c.field_count / c.theme_count),
       'perf_theme_' || g,
       'PERF테마 ' || g,
       '성능 측정용 가상 테마 ' || g,
       c.anchor, c.anchor
FROM _cfg c, generate_series(1, c.theme_count) g;

INSERT INTO issue (id, theme_id, name, first_seen_at, created_at, updated_at)
SELECT g,
       1 + (g % c.theme_count),
       'PERF이슈 ' || g,
       c.anchor - (pg_temp.prand(g, 13) * c.spread_hours || ' hours')::interval,
       c.anchor, c.anchor
FROM _cfg c, generate_series(1, c.issue_count) g;


-- ----------------------------------------------------------------------------
-- 기사 본문: article_count 건
--
-- 쏠림은 power(prand, skew_exp) 로 만듭니다. prand 는 균등분포이고,
-- 여기에 3제곱을 하면 값이 0 쪽으로 몰립니다. 인덱스 1번(=국가 A0)이
-- 가장 많고 뒤로 갈수록 급격히 줄어드는, 뉴스 발행량과 비슷한 형태입니다.
-- ----------------------------------------------------------------------------
INSERT INTO article (
    id, publisher_country_code, theme_id, issue_id,
    publisher, url, original_title, translated_title,
    crawled_at, theme_relevance_score, issue_similarity, tone_score,
    summary, created_at, published_at, issue_assigned_at, deleted_at
)
SELECT
    'perf-' || lpad(g::text, 8, '0'),

    pg_temp.ccode(1 + floor(c.country_count * power(pg_temp.prand(g, 2), c.skew_exp))::int),

    1 + floor(c.theme_count * power(pg_temp.prand(g, 3), c.skew_exp))::int,

    -- 15% 는 이슈 미배정
    CASE WHEN pg_temp.prand(g, 4) < 0.15 THEN NULL
         ELSE 1 + floor(c.issue_count * pg_temp.prand(g, 14))::int END,

    'Perf Publisher ' || (1 + (g % 500)),

    'https://perf.example.com/' || to_char(g, 'FM00000000') || '/article-' || g,

    -- 운영과 비슷한 길이(약 95자)를 유지합니다. 짧게 만들면 테이블이 작아져
    -- 전부 캐시에 들어가고 I/O 특성을 관찰할 수 없습니다.
    'Perf article ' || g || ' - ' || repeat('lorem ipsum dolor sit amet consectetur ', 2),

    'PERF 성능 측정 기사 ' || g || ' 번역 제목 ' || repeat('가상 제목 조각 ', 2),

    pub.at + interval '8 minutes',

    (0.80 + 0.20 * pg_temp.prand(g, 7))::numeric(4,3),
    (0.80 + 0.20 * pg_temp.prand(g, 8))::numeric(4,3),
    (20 + 60 * pg_temp.prand(g, 6))::numeric(5,2),

    -- 약 450바이트(한글 150자)로 운영 요약문 길이에 맞춥니다.
    repeat('이 기사는 성능 측정을 위해 생성된 가상 데이터입니다. ', 3) || g,

    pub.at + interval '8 minutes',
    pub.at,
    pub.at + interval '10 minutes',

    -- 약 2% soft delete
    CASE WHEN pg_temp.prand(g, 9) < 0.02
         THEN pub.at + interval '1 hour' END

FROM _cfg c,
     generate_series(1, c.article_count) g,
     LATERAL (
         SELECT c.anchor
                - (pg_temp.prand(g, 5) * c.spread_hours || ' hours')::interval
                AS at
     ) pub;


-- ----------------------------------------------------------------------------
-- 기사-국가 언급: 기사당 1~4건 (평균 약 2.5건 => 약 1.25M 행)
--
-- PK 가 (article_id, country_code) 이므로 같은 국가가 중복 추첨될 수 있습니다.
-- ON CONFLICT DO NOTHING 으로 흘려보내며, 그 결과 기사별 언급 수가 자연스럽게
-- 불균일해집니다 (실제 데이터와 비슷한 성질).
-- ----------------------------------------------------------------------------
INSERT INTO article_country_mention (article_id, country_code)
SELECT a.id,
       pg_temp.ccode(1 + floor(c.country_count * power(pg_temp.prand(seq.g, 20 + k), c.skew_exp))::int)
FROM _cfg c,
     article a,
     LATERAL (SELECT substring(a.id from 6)::bigint AS g) seq,
     LATERAL generate_series(1, 1 + floor(4 * pg_temp.prand(seq.g, 15))::int) k
WHERE a.id LIKE 'perf-%'
ON CONFLICT DO NOTHING;


COMMIT;


-- ----------------------------------------------------------------------------
-- 통계 갱신: 반드시 필요합니다.
-- ANALYZE 없이 측정하면 플래너가 통계 없이 추정하므로 플랜이 실제 운영과
-- 달라지고, 측정값에 의미가 없어집니다.
-- ----------------------------------------------------------------------------
ANALYZE country;
ANALYZE field;
ANALYZE theme;
ANALYZE issue;
ANALYZE article;
ANALYZE article_country_mention;


-- ----------------------------------------------------------------------------
-- 생성 결과 확인
-- ----------------------------------------------------------------------------
SELECT 'article' AS table_name, count(*) AS rows FROM article
UNION ALL SELECT 'article_country_mention', count(*) FROM article_country_mention
UNION ALL SELECT 'country', count(*) FROM country
UNION ALL SELECT 'theme',   count(*) FROM theme
UNION ALL SELECT 'field',   count(*) FROM field
UNION ALL SELECT 'issue',   count(*) FROM issue
ORDER BY 1;

-- 테이블 물리 크기 (shared_buffers 와 비교해 보십시오)
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       pg_size_pretty(pg_relation_size(relid))       AS heap_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('article', 'article_country_mention')
ORDER BY pg_total_relation_size(relid) DESC;

-- 최근 24시간 윈도우에 걸리는 기사 수와 상위 발행국
--   전체의 약 1/3, 상위 국가가 뚜렷하게 쏠려 있어야 정상입니다.
SELECT publisher_country_code,
       count(*) AS articles_24h,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM article
WHERE published_at >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') - INTERVAL '24 hours'
  AND published_at <  (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')
  AND deleted_at IS NULL
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
