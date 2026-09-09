-- ============================================================================
-- witw 집계 쿼리 성능 측정 세트
--
-- 대상: ThemeRepository / CountryRepository 의 네이티브 쿼리 5개 (원문 그대로)
-- 실행: psql -h localhost -U postgres -d witw -f scripts/perf/measure.sql
--       (pgAdmin 쿼리 툴에도 붙여넣을 수 있음 — psql 메타명령을 쓰지 않음)
--
-- 선행 조건: scripts/perf/generate-bulk.sql 로 데이터를 생성해 두어야 합니다.
--
-- ---------------------------------------------------------------------------
-- 측정 방법 (이 순서를 지켜야 숫자가 의미를 갖습니다)
-- ---------------------------------------------------------------------------
-- 1. 이 파일을 3회 이상 연속 실행하고 마지막 결과를 씁니다.
--    첫 실행은 콜드 캐시라 느립니다. 플랜의 'shared read' 가 'shared hit' 으로
--    바뀌는지 보면 워밍 여부를 알 수 있습니다.
-- 2. 변경은 한 번에 하나만 합니다. 인덱스를 두 개 동시에 넣으면 어느 쪽
--    효과인지 알 수 없습니다.
-- 3. 인덱스를 만든 뒤에는 반드시 ANALYZE 를 다시 돌립니다.
-- 4. 결과는 DOCS/PERF.md 에 환경 정보와 함께 기록합니다.
--    절대 시간은 머신마다 다릅니다. 팀원과 공유할 때는 before/after 배수로
--    이야기하는 편이 안전합니다.
--
-- ---------------------------------------------------------------------------
-- 파라미터
-- ---------------------------------------------------------------------------
-- 국가 코드는 아래 쿼리 안에 리터럴 'A0' 로 박혀 있습니다. 바꾸려면 전체 치환
-- 하십시오.
--
-- 임시 테이블이나 서브쿼리로 파라미터화하면 안 됩니다.
--   나쁨: publisher_country_code = (SELECT code FROM _param)
--   좋음: publisher_country_code = 'A0'
-- 플래너는 리터럴 값을 통계에 대입해서 선택도를 추정합니다. 서브쿼리로 감싸면
-- 그 값을 모르는 상태로 계획을 세우므로 플랜 자체가 달라지고, 측정이 무의미해
-- 집니다.
--
-- 쏠린 분포이므로 국가에 따라 플래너 선택이 달라집니다. 둘 다 재보십시오.
--   'A0' : 전체의 약 30% — 선택도가 낮아 seq scan 이 유리할 수 있음
--   'C5' : 롱테일 — 선택도가 높아 index scan 이 유리
-- 인덱스가 "효과 없다"는 결론이 나오면 롱테일 국가로도 재보아야 합니다.
-- ============================================================================


-- ############################################################################
-- A. 환경 스냅샷 — 결과를 기록할 때 이 값들을 함께 적으십시오.
--    이게 없으면 나중에 두 사람의 숫자가 왜 다른지 설명할 수 없습니다.
-- ############################################################################

SELECT name, setting, unit
FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem', 'effective_cache_size',
               'max_parallel_workers_per_gather', 'random_page_cost',
               'track_io_timing', 'server_version')
ORDER BY name;

SELECT relname AS table_name,
       (SELECT count(*) FROM pg_index i WHERE i.indrelid = relid) AS indexes,
       pg_size_pretty(pg_relation_size(relid))       AS heap,
       pg_size_pretty(pg_indexes_size(relid))        AS idx,
       pg_size_pretty(pg_total_relation_size(relid)) AS total
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('article', 'article_country_mention', 'theme', 'field', 'country')
ORDER BY pg_total_relation_size(relid) DESC;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('article', 'article_country_mention')
ORDER BY tablename, indexname;


-- ############################################################################
-- B. 워밍업 — 결과는 버립니다. 캐시를 채우는 목적입니다.
-- ############################################################################

SELECT count(*) FROM article
WHERE published_at >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') - INTERVAL '24 hours'
  AND deleted_at IS NULL;

SELECT count(*) FROM article_country_mention;


-- ############################################################################
-- C. 측정
-- ############################################################################

-- ===== 1. ThemeRepository.findThemesByField =====
-- 국가 필터가 없습니다. 24시간 윈도우 + theme 조인만으로 전체 분야/테마를 집계.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul' AS end_at
)
SELECT f.id AS "fieldId", f.name AS "fieldName",
       t.id AS "themeId", t.name AS "themeName",
       COUNT(a.id) AS "articleCount24"
FROM field f
CROSS JOIN bounds b
LEFT JOIN theme t ON t.field_id = f.id
LEFT JOIN article a ON a.theme_id = t.id
                   AND a.deleted_at IS NULL
                   AND a.published_at >= b.end_at - INTERVAL '24 hours'
                   AND a.published_at < b.end_at
GROUP BY f.id, f.name, t.id, t.name
ORDER BY f.id, COUNT(a.id) DESC, t.id;


-- ===== 2. ThemeRepository.findPopularThemesWithHourlyTrend =====
-- CTE 3개 + generate_series 24버킷. theme_counts 를 두 번 스캔합니다.
-- work_mem 부족 시 'Sort Method: external merge Disk:' 가 찍히는지 확인하십시오.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT date_trunc('hour', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')
           + INTERVAL '1 hour' AS end_at
),
theme_counts AS (
    SELECT t.id AS theme_id,
           f.name AS field_name,
           t.name AS theme_name,
           date_trunc('hour', a.published_at) AS bucket_start,
           COUNT(*) AS article_count
    FROM article a
    JOIN theme t ON t.id = a.theme_id
    JOIN field f ON f.id = t.field_id
    CROSS JOIN bounds b
    WHERE a.publisher_country_code = 'A0'
      AND a.published_at >= b.end_at - INTERVAL '24 hours'
      AND a.published_at < b.end_at
      AND a.deleted_at IS NULL
    GROUP BY t.id, f.name, t.name, date_trunc('hour', a.published_at)
),
popular_themes AS (
    SELECT theme_id, field_name, theme_name,
           SUM(article_count)::bigint AS article_count_24
    FROM theme_counts
    GROUP BY theme_id, field_name, theme_name
    ORDER BY article_count_24 DESC, theme_id
    LIMIT 5
),
buckets AS (
    SELECT generate_series(
        b.end_at - INTERVAL '24 hours',
        b.end_at - INTERVAL '1 hour',
        INTERVAL '1 hour'
    ) AS bucket_start
    FROM bounds b
)
SELECT p.theme_id AS "themeId",
       p.field_name AS "fieldName",
       p.theme_name AS "themeName",
       p.article_count_24 AS "articleCount24",
       b.bucket_start AS "bucketStart",
       COALESCE(tc.article_count, 0) AS "articleCount"
FROM popular_themes p
CROSS JOIN buckets b
LEFT JOIN theme_counts tc
       ON tc.theme_id = p.theme_id
      AND tc.bucket_start = b.bucket_start
ORDER BY p.article_count_24 DESC, p.theme_id, b.bucket_start;


-- ===== 3. ThemeRepository.findPopularThemes =====
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
)
SELECT t.id     AS "themeId",
       f.name   AS "fieldName",
       t.name   AS "themeName",
       COUNT(*) AS "articleCount24"
FROM article a
JOIN theme t ON t.id = a.theme_id
JOIN field f ON f.id = t.field_id
CROSS JOIN bounds b
WHERE a.publisher_country_code = 'A0'
  AND a.published_at >= b.end_at - INTERVAL '24 hours'
  AND a.published_at <  b.end_at
  AND a.deleted_at IS NULL
GROUP BY t.id, f.name, t.name
ORDER BY COUNT(*) DESC, t.id
LIMIT 5;


-- ===== 4. CountryRepository.findOutgoingMentionRatios =====
-- article(발행국 필터) -> mention(article_id 조인) 방향.
-- PK (article_id, country_code) 의 선행 컬럼이 article_id 이므로 조인은 PK 로 커버됩니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
),
mention_counts AS (
    SELECT m.country_code AS country_code,
           COUNT(*)       AS mention_count
    FROM article a
    JOIN article_country_mention m ON m.article_id = a.id
    CROSS JOIN bounds b
    WHERE a.publisher_country_code = 'A0'
      AND m.country_code <> 'A0'
      AND a.deleted_at IS NULL
      AND a.published_at >= b.end_at - INTERVAL '24 hours'
      AND a.published_at <  b.end_at
    GROUP BY m.country_code
)
SELECT c.country_code AS "countryCode",
       c.name_ko      AS "countryName",
       mc.mention_count::double precision
           / SUM(mc.mention_count) OVER () AS "mentionRatio"
FROM mention_counts mc
JOIN country c ON c.country_code = mc.country_code
ORDER BY mc.mention_count DESC, c.country_code
LIMIT 5;


-- ===== 5. CountryRepository.findIncomingMentionRatios =====
-- mention(country_code 필터) -> article 조인 방향.
-- country_code 는 PK 의 두 번째 컬럼이라 선행 컬럼이 아닙니다.
-- => 이 쿼리가 인덱스 부재의 영향을 가장 크게 받습니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
),
mention_counts AS (
    SELECT a.publisher_country_code AS country_code,
           COUNT(*)                 AS mention_count
    FROM article_country_mention m
    JOIN article a ON a.id = m.article_id
    CROSS JOIN bounds b
    WHERE m.country_code = 'A0'
      AND a.publisher_country_code <> 'A0'
      AND a.deleted_at IS NULL
      AND a.published_at >= b.end_at - INTERVAL '24 hours'
      AND a.published_at <  b.end_at
    GROUP BY a.publisher_country_code
)
SELECT c.country_code AS "countryCode",
       c.name_ko      AS "countryName",
       mc.mention_count::double precision
           / SUM(mc.mention_count) OVER () AS "mentionRatio"
FROM mention_counts mc
JOIN country c ON c.country_code = mc.country_code
ORDER BY mc.mention_count DESC, c.country_code
LIMIT 5;


-- ############################################################################
-- D. 인덱스 후보 — 주석을 하나씩만 풀어서 적용하고 C 를 재측정하십시오.
--    적용 후 ANALYZE 를 반드시 다시 돌립니다.
-- ############################################################################

-- (1) 국가 + 시간 윈도우. 쿼리 2, 3, 4 가 대상입니다.
--     deleted_at IS NULL 부분 인덱스로 만들면 soft delete 행을 인덱스에서
--     아예 배제하므로 크기가 줄고 선택도가 좋아집니다.
--     쿼리에 a.deleted_at IS NULL 이 문자 그대로 있으므로 부분 인덱스가 매칭됩니다.
--
-- CREATE INDEX idx_article_country_published
--     ON article (publisher_country_code, published_at)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- (2) 시간 윈도우 단독. 쿼리 1 (findThemesByField) 이 대상입니다.
--     국가 필터가 없으므로 (1) 번 인덱스로는 커버되지 않습니다.
--     theme_id 를 뒤에 붙이면 인덱스만으로 집계가 가능해질 수 있습니다 (covering).
--
-- CREATE INDEX idx_article_published_theme
--     ON article (published_at, theme_id)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- (3) 언급 역방향 조회. 쿼리 5 가 대상입니다.
--     PK 가 (article_id, country_code) 라서 country_code 단독 조회를 못 탑니다.
--     선행 컬럼을 country_code 로 뒤집은 인덱스가 필요합니다.
--
-- CREATE INDEX idx_mention_country_article
--     ON article_country_mention (country_code, article_id);
-- ANALYZE article_country_mention;

-- 주의: 코드에 남아 있는 TODO 중 article_country_mention (article_id) 단독
--       인덱스는 불필요합니다. PK 의 선행 컬럼이 이미 article_id 이므로
--       완전히 중복입니다.


-- ############################################################################
-- E. 진단 보조
-- ############################################################################

-- 플래너가 인덱스를 안 쓸 때, 인덱스가 없어서인지 플래너 판단인지 구분합니다.
-- 세션 한정이며 진단 목적으로만 쓰십시오. 이 상태의 수치를 성능 결과로
-- 기록해서는 안 됩니다.
--
-- SET enable_seqscan = off;
--   ... C 섹션 재실행 ...
-- RESET enable_seqscan;

-- 정렬/해시가 디스크로 흘러내릴 때 work_mem 이 원인인지 확인합니다.
--
-- SET work_mem = '64MB';
--   ... C 섹션 재실행 ...
-- RESET work_mem;
