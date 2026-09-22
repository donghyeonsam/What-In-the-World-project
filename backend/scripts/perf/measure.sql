-- ============================================================================
-- witw 쿼리 성능 측정 세트
--
-- 대상: Repository 네이티브 쿼리 전체 (원문 그대로)
-- 실행: docker exec witw-postgres-perf psql -U postgres -d witw -f /tmp/measure.sql
--       (pgAdmin 쿼리 툴에도 붙여넣을 수 있음 — psql 메타명령을 쓰지 않음)
--
-- 선행 조건
--   1. 스키마가 적용돼 있어야 합니다. perf 컨테이너는 빈 Postgres 라서
--      Flyway 가 돈 적이 없습니다. src/main/resources/db/migration 을
--      V1 → V2 → ... → V6 → V6_1 → V7 → V8 순서로 먼저 적용하십시오.
--      (V6_1 은 LOCK TABLE 을 쓰므로 psql --single-transaction 필요.
--       파일명 정렬은 V6_1 이 V6 보다 앞서므로 순서를 명시해야 합니다.)
--   2. scripts/perf/generate-bulk.sql 로 데이터를 생성해 두어야 합니다.
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
-- 4. 읽기만 재지 마십시오. Kafka 컨슈머(DbWriterService)가 article 을 계속
--    INSERT 하므로 인덱스는 쓰기를 느리게 합니다.
--    scripts/perf/write-test.sql 을 같이 돌려서 쓰기 저하를 확인하십시오.
-- 5. 결과는 DOCS/PERF.md 에 환경 정보와 함께 기록합니다.
--    절대 시간은 머신마다 다릅니다. 팀원과 공유할 때는 before/after 배수로
--    이야기하는 편이 안전합니다.
--
-- ---------------------------------------------------------------------------
-- 섹션 구성 — 쿼리를 성격별로 나눴습니다
-- ---------------------------------------------------------------------------
-- C. 시간 윈도우가 있는 쿼리       → 범위 인덱스 대상
--      24시간 구간만 읽으면 되므로 데이터가 쌓여도 읽는 양이 안 늘어납니다.
--      인덱스로 해결되는 부류입니다.
--
-- D. 정렬 + LIMIT 쿼리            → 정렬 서빙 인덱스 대상
--      시간 제한이 없지만 상위 N건만 필요합니다. 인덱스가 정렬 순서를
--      제공하면 N건만 읽고 멈출 수 있습니다. C 와 인덱스 모양이 다릅니다.
--
-- E. 전체 집계 쿼리                → 인덱스로 해결 불가, 반정규화 검토 대상
--      시간 제한도 LIMIT 도 없이 전체를 셉니다. Postgres 는 MVCC 때문에
--      빠른 count 가 없어서 인덱스를 만들어도 전부 훑습니다.
--      누적량에 비례해 계속 느려집니다.
--      스키마에 이미 article_summary / country_tone 테이블이 있지만
--      현재 아무 코드도 쓰지 않습니다. 되살릴지 지울지 정해야 합니다.
--
-- F. 참고 쿼리                     → 이미 인덱스가 있거나 대상이 작음
--
-- ---------------------------------------------------------------------------
-- 파라미터
-- ---------------------------------------------------------------------------
-- 쿼리 안에 리터럴로 박혀 있습니다. 바꾸려면 전체 치환하십시오.
--
-- 임시 테이블이나 서브쿼리로 파라미터화하면 안 됩니다.
--   나쁨: publisher_country_code = (SELECT code FROM _param)
--   좋음: publisher_country_code = 'A0'
-- 플래너는 리터럴 값을 통계에 대입해서 선택도를 추정합니다. 서브쿼리로 감싸면
-- 그 값을 모르는 상태로 계획을 세우므로 플랜 자체가 달라지고, 측정이 무의미해
-- 집니다.
--
-- 쏠린 분포이므로 값에 따라 플래너 선택이 달라집니다. 둘 다 재보십시오.
--   'A0' : 전체의 약 30% — 선택도가 낮아 seq scan 이 유리할 수 있음
--   'C5' : 롱테일 — 선택도가 높아 index scan 이 유리
-- 인덱스가 "효과 없다"는 결론이 나오면 롱테일 값으로도 재보아야 합니다.
--
-- theme_id / issue_id 도 마찬가지입니다. 아래 A-2 섹션이 실제 상위/하위
-- 값을 뽑아주니, 기본값(theme 1 / issue 1)이 한쪽에 치우쳐 있으면
-- 거기서 나온 값으로 치환하십시오.
-- ============================================================================


-- ############################################################################
-- 0. 연결 대상 가드 — 여기서 멈추면 잘못된 DB 에 붙은 것입니다.
--
-- perf 데이터는 article.id 가 'perf-' 로 시작합니다 (generate-bulk.sql).
-- 실데이터 DB 에 연결한 채로 이 파일을 돌리면 측정값이 무의미하므로
-- 21개를 다 돌린 뒤가 아니라 첫 줄에서 멈춥니다.
--
-- perf 컨테이너 접속 정보:
--   host 127.0.0.1  port 15432  db witw  user postgres  password perf
--   (로컬 설치본은 보통 5432 입니다. 포트를 확인하십시오.)
-- ############################################################################

DO $guard$
DECLARE
    total   bigint;
    perfrow bigint;
BEGIN
    SELECT count(*) INTO total   FROM article;
    SELECT count(*) INTO perfrow FROM article WHERE id LIKE 'perf-%';

    IF total = 0 THEN
        RAISE EXCEPTION
            'article 이 비어 있습니다. generate-bulk.sql 을 먼저 실행하십시오.';
    ELSIF perfrow = 0 THEN
        RAISE EXCEPTION
            'perf 데이터셋이 아닙니다 (article %행, perf- 접두어 0행). 연결 대상을 확인하십시오. 포트 15432 가 맞습니까?', total;
    END IF;
END
$guard$;



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
-- A-2. 파라미터 확인
--
-- 아래 쿼리들에 박아둔 theme_id / issue_id 가 데이터가 거의 없는 값이면
-- 측정이 무의미합니다. 상위(head)와 하위(tail)를 뽑아서 확인하십시오.
-- ############################################################################

-- 기사가 가장 많은 테마 3개 / 가장 적은 테마 3개
(SELECT 'theme head' AS bucket, theme_id, count(*) AS articles
 FROM article WHERE deleted_at IS NULL
 GROUP BY theme_id ORDER BY count(*) DESC LIMIT 3)
UNION ALL
(SELECT 'theme tail', theme_id, count(*)
 FROM article WHERE deleted_at IS NULL
 GROUP BY theme_id ORDER BY count(*) ASC LIMIT 3);

-- 기사가 가장 많은 이슈 3개 / 가장 적은 이슈 3개
(SELECT 'issue head' AS bucket, issue_id, count(*) AS articles
 FROM article WHERE deleted_at IS NULL AND issue_id IS NOT NULL
 GROUP BY issue_id ORDER BY count(*) DESC LIMIT 3)
UNION ALL
(SELECT 'issue tail', issue_id, count(*)
 FROM article WHERE deleted_at IS NULL AND issue_id IS NOT NULL
 GROUP BY issue_id ORDER BY count(*) ASC LIMIT 3);


-- ############################################################################
-- B. 워밍업 — 결과는 버립니다. 캐시를 채우는 목적입니다.
-- ############################################################################

SELECT count(*) FROM article
WHERE published_at >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') - INTERVAL '24 hours'
  AND deleted_at IS NULL;

SELECT count(*) FROM article_country_mention;


-- ############################################################################
-- C. 시간 윈도우가 있는 쿼리 — 범위 인덱스 대상
-- ############################################################################

-- ===== C1. ThemeRepository.findThemesByField =====
-- 2026-09-14 재작성 반영. article 집계를 counts 서브쿼리로 분리했습니다.
-- 원본은 12만 행이 LEFT JOIN 체인을 통과한 뒤 집계됐고, article 스캔이
-- 조인 안쪽에 갇혀 병렬 실행도 막혔습니다 (Seq Scan loops=1).
-- counts 안은 LEFT JOIN 이 아니라 COUNT(*) 가 안전하고, theme_id 만 참조하므로
-- (published_at, theme_id) 인덱스가 있으면 Index Only Scan 이 잡힙니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul' AS end_at
),
counts AS (
    SELECT a.theme_id, COUNT(*) AS article_count
    FROM article a
    CROSS JOIN bounds b
    WHERE a.deleted_at IS NULL
      AND a.published_at >= b.end_at - INTERVAL '24 hours'
      AND a.published_at <  b.end_at
    GROUP BY a.theme_id
)
SELECT f.id AS "fieldId", f.name AS "fieldName",
       t.id AS "themeId", t.name AS "themeName",
       COALESCE(c.article_count, 0) AS "articleCount24"
FROM field f
LEFT JOIN theme t  ON t.field_id = f.id
LEFT JOIN counts c ON c.theme_id = t.id
ORDER BY f.id, COALESCE(c.article_count, 0) DESC, t.id;


-- ===== C2. ThemeRepository.findPopularThemesWithHourlyTrend =====
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


-- ===== C3. ThemeRepository.findPopularThemes =====
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


-- ===== C4. CountryRepository.findOutgoingMentionRatios =====
-- article 에서 국가로 필터한 뒤 mention 을 article_id 로 조인합니다.
-- mention PK 의 선행 컬럼이 article_id 이므로 이 방향은 PK 로 커버됩니다.
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


-- ===== C5. CountryRepository.findIncomingMentionRatios =====
-- 역방향입니다. mention.country_code 로 먼저 거릅니다.
-- PK 선행 컬럼이 article_id 라서 이 조회는 PK 를 못 탑니다.
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


-- ===== C6. ArticleRepository.countArticlesLast24Hours (전체) =====
-- 파라미터가 둘 다 NULL 인 경우 — 대시보드 전체 카운트.
--
--
-- 예전에는 이 쿼리만 상한(published_at < end_at)이 없고 하한만 KST 라
-- 세션 타임존에 따라 윈도우가 어긋났습니다. 코드에서 다른 24시간 쿼리들과
-- 같은 bounds CTE 로 통일했고 여기도 맞췄습니다.
--
-- 주의: V9 헤더의 "countArticlesLast24Hours 12배" 는 상한이 없던 시절의
-- 측정치입니다. 상한이 생기면서 플래너 선택이 달라질 수 있으니
-- 이 항목은 재측정 대상입니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
)
SELECT COUNT(*) FROM article a
CROSS JOIN bounds b
WHERE a.deleted_at IS NULL
  AND a.published_at >= b.end_at - INTERVAL '24 hours'
  AND a.published_at <  b.end_at
  AND (CAST(NULL AS TEXT) IS NULL OR a.publisher_country_code = NULL)
  AND (CAST(NULL AS BIGINT) IS NULL OR a.issue_id = NULL);


-- ===== C7. ArticleRepository.countArticlesLast24Hours (국가 지정) =====
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
)
SELECT COUNT(*) FROM article a
CROSS JOIN bounds b
WHERE a.deleted_at IS NULL
  AND a.published_at >= b.end_at - INTERVAL '24 hours'
  AND a.published_at <  b.end_at
  AND (CAST('A0' AS TEXT) IS NULL OR a.publisher_country_code = 'A0')
  AND (CAST(NULL AS BIGINT) IS NULL OR a.issue_id = NULL);


-- ===== C8. ArticleRepository.getCountryRankByArticleCounts =====
-- country 40개 x country_counts 자기 비교.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
),
country_counts AS (
    SELECT c.country_code  AS country_code,
           COUNT(a.id)     AS article_count
    FROM country c
    CROSS JOIN bounds b
    LEFT JOIN article a
           ON a.publisher_country_code = c.country_code
          AND a.deleted_at IS NULL
          AND a.published_at >= b.end_at - INTERVAL '24 hours'
          AND a.published_at <  b.end_at
    GROUP BY c.country_code
)
SELECT (SELECT COUNT(*) + 1
        FROM country_counts cc
        WHERE cc.article_count > target.article_count)
FROM country_counts target
WHERE target.country_code = 'A0';


-- ===== C9. ArticleRepository.findRepresentArticlesByCountry =====
-- published_at 범위 + theme_relevance_score 정렬. 범위와 정렬 컬럼이 달라서
-- 인덱스 하나로 둘 다 해결할 수 없습니다. 어느 쪽을 태울지가 설계 판단입니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
)
SELECT a.id                AS "articleId",
       a.translated_title  AS "articleTitle",
       a.tone_score        AS "articleToneScore",
       a.publisher         AS "articlePublisher",
       a.published_at      AS "publishedAt"
FROM article a
CROSS JOIN bounds b
WHERE a.publisher_country_code = 'A0'
  AND a.deleted_at IS NULL
  AND a.published_at >= b.end_at - INTERVAL '24 hours'
  AND a.published_at <  b.end_at
ORDER BY a.theme_relevance_score DESC, a.id
LIMIT 10;


-- ===== C10. IssueRepository.findGlobalIssueRankLast24Hours =====
-- 24시간 윈도우 + issue_id 별 집계. 국가 필터가 없습니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
),
top_issues AS (
    SELECT a.issue_id  AS issue_id,
           COUNT(*)    AS article_count
    FROM article a
    CROSS JOIN bounds b
    WHERE a.deleted_at IS NULL
      AND a.issue_id IS NOT NULL
      AND a.published_at >= b.end_at - INTERVAL '24 hours'
      AND a.published_at < b.end_at
    GROUP BY a.issue_id
    ORDER BY article_count DESC, a.issue_id
    LIMIT 10
)
SELECT i.id             AS "issueId",
       f.name           AS "fieldName",
       t.name           AS "themeName",
       i.name           AS "issueName",
       ti.article_count AS "articleCount",
       i.first_seen_at  AS "firstSeenAt"
FROM top_issues ti
JOIN issue i ON i.id = ti.issue_id
JOIN theme t ON t.id = i.theme_id
JOIN field f ON f.id = t.field_id
ORDER BY ti.article_count DESC, i.id;


-- ===== C11. IssueRepository.findCountryTonesLast24Hours =====
-- issue_id 등치 + 24시간 범위. country 조인 후 통계 집계.
-- 참고: country_tone 테이블이 스키마에 있지만 쓰이지 않고, 이 쿼리가
--       매번 article 에서 직접 계산합니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
WITH bounds AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS end_at
)
SELECT c.country_code                        AS "countryCode",
       c.name_ko                             AS "countryName",
       c.longitude                           AS "longitude",
       c.latitude                            AS "latitude",
       AVG(a.tone_score)::double precision   AS "toneAvg",
       MAX(a.tone_score)::double precision   AS "toneMax",
       MIN(a.tone_score)::double precision   AS "toneMin",
       STDDEV_POP(a.tone_score)::double precision AS "toneSd",
       COUNT(*)                              AS "articleCount"
FROM article a
JOIN country c ON c.country_code = a.publisher_country_code
CROSS JOIN bounds b
WHERE a.issue_id = 1
  AND a.deleted_at IS NULL
  AND a.published_at >= b.end_at - INTERVAL '24 hours'
  AND a.published_at < b.end_at
GROUP BY c.country_code, c.name_ko, c.longitude, c.latitude
ORDER BY AVG(a.tone_score) DESC, c.country_code;


-- ############################################################################
-- D. 정렬 + LIMIT 쿼리 — 정렬 서빙 인덱스 대상
--
-- 시간 제한이 없습니다. 지금은 조건에 맞는 기사를 전부 읽어 정렬한 뒤
-- 10건만 씁니다. 인덱스가 정렬 순서를 제공하면 10건만 읽고 멈출 수 있습니다.
-- 플랜에서 'Sort' 노드가 사라지고 Index Scan 이 LIMIT 에서 조기 종료하는지
-- 보십시오. C 섹션과 인덱스 모양이 다릅니다.
-- ############################################################################

-- ===== D1. ArticleRepository.getRepresentArticlesByThemeId =====
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
       a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
       a.published_at AS "publishedAt"
FROM article a
WHERE a.theme_id = 1 AND a.deleted_at IS NULL
ORDER BY a.theme_relevance_score DESC, a.id ASC
LIMIT 10;


-- ===== D2. ArticleRepository.getRepresentArticlesByThemeIdAndCountryCode =====
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
       a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
       a.published_at AS "publishedAt"
FROM article a
WHERE a.theme_id = 1
  AND a.publisher_country_code = 'A0'
  AND a.deleted_at IS NULL
ORDER BY a.theme_relevance_score DESC, a.id ASC
LIMIT 10;


-- ===== D3. ArticleRepository.getRepresentArticlesByIssueId =====
-- NULLS LAST 에 주의하십시오. 인덱스 정렬 순서가 이것과 일치해야 Sort 가
-- 사라집니다. DESC 인덱스의 기본은 NULLS FIRST 입니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
       a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
       a.published_at AS "publishedAt"
FROM article a
WHERE a.issue_id = 1 AND a.deleted_at IS NULL
ORDER BY a.issue_similarity DESC NULLS LAST, a.id ASC
LIMIT 10;


-- ===== D4. ArticleRepository.getRepresentArticlesByIssueIdAndCountryCode =====
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
       a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
       a.published_at AS "publishedAt"
FROM article a
WHERE a.issue_id = 1
  AND a.publisher_country_code = 'A0'
  AND a.deleted_at IS NULL
ORDER BY a.issue_similarity DESC NULLS LAST, a.id ASC
LIMIT 10;


-- ===== D5. IssueRepository.findCountryIssueDetail =====
-- EXISTS 라서 한 건만 찾으면 끝납니다. issue_id 선행 인덱스가 있으면
-- 조기 종료합니다. 정렬은 없지만 "조기 종료" 성격이라 D 로 묶었습니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT i.id           AS "issueId",
       i.name         AS "issueName",
       t.name         AS "themeName",
       f.name         AS "fieldName",
       c.country_code AS "countryCode",
       c.name_ko      AS "countryName"
FROM issue i
JOIN theme t ON t.id = i.theme_id
JOIN field f ON f.id = t.field_id
JOIN country c ON c.country_code = 'A0'
WHERE i.id = 1
  AND EXISTS (
      SELECT 1
      FROM article a
      WHERE a.issue_id = i.id
        AND a.publisher_country_code = c.country_code
        AND a.deleted_at IS NULL
  );


-- ############################################################################
-- E. 전체 집계 쿼리 — 인덱스로 해결 불가, 반정규화 검토 대상
--
-- 시간 제한도 LIMIT 도 없습니다. 데이터가 쌓이는 만큼 계속 느려집니다.
-- 인덱스를 넣어도 인덱스 전체를 훑으므로 상수배 개선에 그칩니다.
--
-- 여기 걸린 쿼리는 인덱스 실험 대상이 아니라 "인덱스로 안 된다"는 근거를
-- 남기는 대상입니다. 인덱스 적용 전후로 재서, 개선이 2배 미만이면
-- article_summary / country_tone 되살리기를 검토하십시오.
--
-- 반정규화 판단 기준 (DOCS/PERF.md 참조):
--   1. 인덱스를 넣고도 화면 예산을 못 맞춘다
--   2. 누적량에 비례해 느려진다 (= 여기 섹션에 있다)
--   3. 갱신 주체가 명확하다 (Kafka 컨슈머? 스케줄러?)
--   4. 최신성 허용치를 정했다 (몇 분까지 오래된 값을 허용하는가)
-- ############################################################################

-- ===== E1. ArticleRepository.countByDeletedAtIsNull =====
-- Spring Data 파생 쿼리. 전체 기사 수.
-- article_summary.total_article_count 가 존재하는 이유입니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT count(*) FROM article a WHERE a.deleted_at IS NULL;


-- ===== E2. IssueRepository.findIssueById =====
-- COUNT DISTINCT 까지 있어서 전체 집계 중에서도 무겁습니다.
-- LEFT JOIN + ON 절 삭제 조건은 의도된 것입니다 (원본 주석 참조).
-- WHERE 로 옮기면 삭제된 기사만 있는 이슈가 행 자체를 잃습니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT  i.id AS "issueId",
        i.name AS "issueName",
        count(a.id) AS "articleCount",
        count(distinct a.publisher_country_code) AS "countryCount"
FROM issue i
LEFT JOIN article a
    ON a.issue_id = i.id
    AND a.deleted_at IS NULL
WHERE i.id = 1
GROUP BY i.id, i.name;


-- ===== E3. IssueRepository.getIssuePreviewByIssueId =====
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT
    i.name AS issueTitle,
    t.name AS themeTitle,
    COUNT(a.id) AS articleCount
FROM issue i
JOIN theme t ON i.theme_id = t.id
LEFT JOIN article a
    ON i.id = a.issue_id
    AND a.deleted_at IS NULL
WHERE i.id = 1
GROUP BY i.id, i.name, t.name;


-- ===== E4. IssueRepository.getPrimaryIssuesByThemeId =====
-- 테마에 속한 이슈 전체를 기사 수로 정렬합니다. LIMIT 이 있지만 집계 후
-- 정렬이라 조기 종료가 안 됩니다. 테마의 모든 기사를 세어야 합니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT i.id AS issueId, i.name AS issueTitle
FROM issue i
JOIN article a ON a.issue_id = i.id
WHERE i.theme_id = 1
    AND a.deleted_at IS NULL
GROUP BY i.id, i.name
ORDER BY count(*) DESC, i.id ASC
LIMIT 10;


-- ############################################################################
-- F. 참고 쿼리 — 이미 인덱스가 있거나 대상이 작음
--
-- 측정은 하되 튜닝 대상은 아닙니다. 회귀 확인용으로 남겨둡니다.
-- ############################################################################

-- ===== F1. IssueRepository.findIssueDetailsByIds =====
-- issue PK 조회 + 작은 테이블 조인. article 을 건드리지 않습니다.
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT i.id   AS "issueId",
       i.name AS "issueName",
       t.name AS "themeName",
       f.name AS "fieldName"
FROM issue i
JOIN theme t ON t.id = i.theme_id
JOIN field f ON f.id = t.field_id
WHERE i.id IN (1, 2, 3, 4, 5);


-- ===== F2. UserRepository.findByEmailIgnoreCase =====
-- V6 의 UK_USERS_EMAIL ON users (LOWER(email)) 함수 인덱스와 정확히 맞습니다.
-- Index Scan 이 나오는지만 확인하십시오. Seq Scan 이면 로그인 경로 문제입니다.
-- (perf 데이터셋에 users 행이 없으면 의미 없는 결과가 나옵니다)
EXPLAIN (ANALYZE, BUFFERS, COSTS, TIMING)
SELECT u.* FROM users u WHERE LOWER(u.email) = LOWER('perf@example.test');


-- ############################################################################
-- G. 인덱스 후보
--
-- 후보 도출 근거와 우선순위는 DOCS/PERF.md 를 보십시오.
-- 주석을 하나씩만 풀어서 적용하고 C~E 를 재측정하십시오.
-- 적용 후 ANALYZE 를 반드시 다시 돌립니다.
--
-- 주의: article 인덱스 상한을 5개로 잡았는데 아래 후보는 그보다 많습니다.
--       전부 넣는 것이 목적이 아니라, 재보고 걸러내는 것이 목적입니다.
--       인덱스를 추가할 때마다 write-test.sql 로 쓰기 저하를 확인하십시오.
-- ############################################################################

-- ---------------------------------------------------------------------------
-- 1순위 — 시간 윈도우 (published_at)
-- ---------------------------------------------------------------------------

-- G1. 국가 + 시간. C2, C3, C4 대상.
--     deleted_at IS NULL 부분 인덱스로 만들면 soft delete 행을 인덱스에서
--     아예 배제하므로 크기가 줄고 선택도가 좋아집니다.
--     쿼리에 a.deleted_at IS NULL 이 문자 그대로 있으므로 매칭됩니다.
--
-- CREATE INDEX idx_article_country_published
--     ON article (publisher_country_code, published_at)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- G2. 시간 단독 + theme. C1 대상 (국가 필터가 없어 G1 로 커버 안 됨).
--
-- CREATE INDEX idx_article_published_theme
--     ON article (published_at, theme_id)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- G2-alt. G2 의 컬럼 순서를 뒤집은 것. C1 은 theme 68개를 각각 탐색할 수도,
--         24시간 구간을 한 번에 훑을 수도 있어서 어느 쪽이 유리한지
--         논리로 정할 수 없습니다. 둘 다 재서 이긴 쪽만 남기십시오.
--         (동시에 두 개를 만들면 안 됩니다 — 하나씩)
--
-- CREATE INDEX idx_article_theme_published
--     ON article (theme_id, published_at)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- G3. 언급 역방향. C5 대상.
--     PK 가 (article_id, country_code) 라서 country_code 단독 조회를 못 탑니다.
--     선행 컬럼을 뒤집은 인덱스가 필요합니다.
--
-- CREATE INDEX idx_mention_country_article
--     ON article_country_mention (country_code, article_id);
-- ANALYZE article_country_mention;

-- ---------------------------------------------------------------------------
-- 2순위 — 정렬 서빙 (D 섹션)
-- ---------------------------------------------------------------------------

-- G4. 테마별 대표 기사. D1, D2 대상.
--     ORDER BY theme_relevance_score DESC, id ASC 와 인덱스 순서가 일치해야
--     Sort 노드가 사라지고 LIMIT 에서 조기 종료합니다.
--
-- CREATE INDEX idx_article_theme_relevance
--     ON article (theme_id, theme_relevance_score DESC, id ASC)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- G5. 이슈별 대표 기사. D3, D4, D5 대상.
--     NULLS LAST 를 명시해야 합니다. DESC 의 기본은 NULLS FIRST 라서
--     빼먹으면 정렬 순서가 안 맞아 Sort 가 그대로 남습니다.
--
-- CREATE INDEX idx_article_issue_similarity
--     ON article (issue_id, issue_similarity DESC NULLS LAST, id ASC)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- ---------------------------------------------------------------------------
-- (G6 삭제됨 — article (publisher_country_code, created_at))
--
-- ArticleRepository 의 24시간 기준이 created_at -> published_at 으로 통일되면서
-- 불필요해졌습니다. C7, C8, C9 는 이제 G1 이 커버합니다.
-- 이 변경으로 article 후보가 6개에서 5개로 줄어 상한에 맞게 되었습니다.
--
-- 되돌릴 일이 생기면(요구사항 재확인 등) 이 항목을 복구하십시오:
--   CREATE INDEX idx_article_country_created
--       ON article (publisher_country_code, created_at)
--       WHERE deleted_at IS NULL;
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 3순위 — 이슈 시간 집계
-- ---------------------------------------------------------------------------

-- G7. 이슈 + 시간. C11 대상, C10 도 부분적으로.
--     G5 와 선행 컬럼이 같지만(issue_id) 두 번째 컬럼이 달라서 별개입니다.
--     G5 를 먼저 넣고 C11 이 충분히 빨라지면 이건 불필요할 수 있습니다.
--     반드시 G5 측정 후에 판단하십시오.
--
-- CREATE INDEX idx_article_issue_published
--     ON article (issue_id, published_at)
--     WHERE deleted_at IS NULL;
-- ANALYZE article;

-- ---------------------------------------------------------------------------
-- 기각된 후보 — 만들지 마십시오
-- ---------------------------------------------------------------------------
-- * article_country_mention (article_id) 단독
--     PK 의 선행 컬럼이 이미 article_id 이므로 완전 중복입니다.
--     코드에 남은 TODO 주석(CountryRepository.java)은 이 근거로 닫으십시오.
--
-- * article (theme_id) / (issue_id) / (publisher_country_code) 단독
--     G1/G4/G5/G7 의 선행 컬럼에 이미 포함됩니다. FK 라서 필요해 보이지만
--     복합 인덱스의 선행 컬럼이면 단독 인덱스는 불필요합니다.
--
-- * article (deleted_at)
--     부분 인덱스 WHERE 절로 처리하는 편이 항상 낫습니다.
--     soft delete 가 2% 뿐이라 선택도도 나쁩니다.


-- ############################################################################
-- H. 진단 보조
-- ############################################################################

-- 플래너가 인덱스를 안 쓸 때, 인덱스가 없어서인지 플래너 판단인지 구분합니다.
-- 세션 한정이며 진단 목적으로만 쓰십시오. 이 상태의 수치를 성능 결과로
-- 기록해서는 안 됩니다.
--
-- SET enable_seqscan = off;
--   ... C~E 섹션 재실행 ...
-- RESET enable_seqscan;

-- 정렬/해시가 디스크로 흘러내릴 때 work_mem 이 원인인지 확인합니다.
--
-- SET work_mem = '64MB';
--   ... C~E 섹션 재실행 ...
-- RESET work_mem;

-- 만든 인덱스가 실제로 쓰이는지 확인합니다. idx_scan = 0 이면 한 번도
-- 쓰이지 않은 것이므로 기각 대상입니다.
--
-- SELECT indexrelname, idx_scan,
--        pg_size_pretty(pg_relation_size(indexrelid)) AS size
-- FROM pg_stat_user_indexes
-- WHERE relname IN ('article', 'article_country_mention')
-- ORDER BY idx_scan;

-- 총 소모 시간 상위 쿼리. 평균이 아니라 total_exec_time 으로 봐야 합니다.
-- 5ms 쿼리가 10만 번이면 100ms 쿼리 10번보다 큰 문제입니다.
--
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
-- SELECT calls, round(total_exec_time) AS total_ms,
--        round(mean_exec_time, 2) AS mean_ms, left(query, 60) AS q
-- FROM pg_stat_statements
-- ORDER BY total_exec_time DESC LIMIT 20;
