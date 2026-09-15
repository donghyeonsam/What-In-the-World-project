-- article 조회 인덱스 5개. 채택 근거와 측정치는 DOCS/PERF.md, scripts/perf/perf_report.md.
-- 50만 건 기준 조회 합계 1485.2ms -> 535.8ms.
--
-- 공통: WHERE deleted_at IS NULL 부분 인덱스. 모든 조회 쿼리에 이 조건이
-- 문자 그대로 들어 있어야 매칭된다.


-- findPopularThemes, findPopularThemesWithHourlyTrend, findOutgoingMentionRatios,
-- countArticlesLast24Hours, getCountryRankByArticleCounts, findRepresentArticlesByCountry
CREATE INDEX idx_article_country_published
    ON article (publisher_country_code, published_at)
    WHERE deleted_at IS NULL;


-- findThemesByField. 집계를 서브쿼리로 분리해 theme_id 만 참조하므로 Index Only Scan 이 잡힌다.
-- COUNT(a.id) 로 되돌리면 힙 접근이 생겨 효과가 사라진다.
CREATE INDEX idx_article_published_theme
    ON article (published_at, theme_id)
    WHERE deleted_at IS NULL;


-- getRepresentArticlesByThemeId(AndCountryCode).
-- ORDER BY theme_relevance_score DESC, id ASC 와 정렬 순서가 일치해야 Sort 노드가 사라진다.
CREATE INDEX idx_article_theme_relevance
    ON article (theme_id, theme_relevance_score DESC, id ASC)
    WHERE deleted_at IS NULL;


-- getRepresentArticlesByIssueId(AndCountryCode), findCountryIssueDetail,
-- findIssueById, getIssuePreviewByIssueId.
-- NULLS LAST 필수. DESC 의 기본값은 NULLS FIRST 라 빼먹으면 쿼리와 순서가 어긋난다.
CREATE INDEX idx_article_issue_similarity
    ON article (issue_id, issue_similarity DESC NULLS LAST, id ASC)
    WHERE deleted_at IS NULL;


-- findCountryTonesLast24Hours, findGlobalIssueRankLast24Hours.
-- 위와 선행 컬럼은 같지만 두 번째 컬럼이 달라 별개 인덱스다.
CREATE INDEX idx_article_issue_published
    ON article (issue_id, published_at)
    WHERE deleted_at IS NULL;


-- 만들지 않은 후보 (되살리지 말 것)
--   article_country_mention (country_code, article_id) : 조합 기여 1.20배로 기준 미달,
--     크기가 힙의 77.9% (기준 30%), 쓰기 증폭 구간
--   article (theme_id, published_at) : 위 2번의 컬럼 순서를 뒤집은 경쟁 후보. 조합 측정에서 패배
--   article (theme_id) / (issue_id) / (publisher_country_code) 단독 : 복합 인덱스 선행 컬럼에 포함
--   article (deleted_at) : 부분 인덱스 WHERE 절로 대체. soft delete 가 2% 뿐이라 선택도도 나쁨
