package com.ssafy.witw.domain.article.dao;

import com.ssafy.witw.domain.article.entity.Article;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public interface ArticleRepository extends JpaRepository<Article, String> {

    long countByDeletedAtIsNull();

    @Query(value = """
            SELECT COUNT(*) FROM article a
            WHERE a.deleted_at IS NULL
              AND a.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul') - INTERVAL '24 hours'
              AND (CAST(:countryCode AS TEXT) IS NULL OR a.publisher_country_code = :countryCode)
              AND (CAST(:issueId AS BIGINT) IS NULL OR a.issue_id = :issueId)
            """, nativeQuery = true)
    long countArticlesLast24Hours(@Param("countryCode") String countryCode, @Param("issueId") Long issueId);

    @Query(value = """
            SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
                   a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
                   a.published_at AS "publishedAt"
            FROM article a
            WHERE a.theme_id = :themeId AND a.deleted_at IS NULL
            ORDER BY a.theme_relevance_score DESC, a.id ASC
            LIMIT :limit
            """, nativeQuery = true)
    List<RepresentArticleProjection> getRepresentArticlesByThemeId(
            @Param("themeId") Long themeId, @Param("limit") int limit);

    @Query(value = """
            SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
                   a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
                   a.published_at AS "publishedAt"
            FROM article a
            WHERE a.theme_id = :themeId
              AND a.publisher_country_code = :countryCode
              AND a.deleted_at IS NULL
            ORDER BY a.theme_relevance_score DESC, a.id ASC
            LIMIT :limit
            """, nativeQuery = true)
    List<RepresentArticleProjection> getRepresentArticlesByThemeIdAndCountryCode(
            @Param("themeId") Long themeId, @Param("countryCode") String countryCode,
            @Param("limit") int limit);

    interface RepresentArticleProjection {
        String getArticleId();
        String getArticleTitle();
        BigDecimal getArticleToneScore();
        String getArticlePublisher();
        LocalDateTime getPublishedAt();
    }

    @Query(value = """
            SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
                   a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
                   a.published_at AS "publishedAt"
            FROM article a
            WHERE a.issue_id = :issueId AND a.deleted_at IS NULL
            ORDER BY a.issue_similarity DESC NULLS LAST, a.id ASC
            LIMIT :limit
            """, nativeQuery = true)
    List<RepresentArticleProjection> getRepresentArticlesByIssueId(
            @Param("issueId") Long issueId, @Param("limit") int limit);

    @Query(value = """
            SELECT a.id AS "articleId", a.translated_title AS "articleTitle",
                   a.tone_score AS "articleToneScore", a.publisher AS "articlePublisher",
                   a.published_at AS "publishedAt"
            FROM article a
            WHERE a.issue_id = :issueId
              AND a.publisher_country_code = :countryCode
              AND a.deleted_at IS NULL
            ORDER BY a.issue_similarity DESC NULLS LAST, a.id ASC
            LIMIT :limit
            """, nativeQuery = true)
    List<RepresentArticleProjection> getRepresentArticlesByIssueIdAndCountryCode(
            @Param("issueId") Long issueId, @Param("countryCode") String countryCode,
            @Param("limit") int limit);



    // 최근 24시간 수집 기사 수 기준 해당 국가의 세계 순위 (동률은 같은 순위, 기사 0건인 국가도 포함)
    // FR-DSB-006이 "수집" 기준이므로 published_at이 아닌 created_at으로 자른다
    // TODO: article (deleted_at, created_at, publisher_country_code) 복합 인덱스 검토
    @Query(value = """
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
                      AND a.created_at >= b.end_at - INTERVAL '24 hours'
                      AND a.created_at <  b.end_at
                GROUP BY c.country_code
            )
            SELECT (SELECT COUNT(*) + 1
                    FROM country_counts cc
                    WHERE cc.article_count > target.article_count)
            FROM country_counts target
            WHERE target.country_code = :countryCode
            """, nativeQuery = true)
    Integer getCountryRankByArticleCounts(@Param("countryCode") String countryCode);

    // 최근 24시간 해당 국가 수집 기사 중 테마 적합도 상위 N건 (기사 수·순위와 같은 기준)
    @Query(value = """
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
            WHERE a.publisher_country_code = :countryCode
              AND a.deleted_at IS NULL
              AND a.created_at >= b.end_at - INTERVAL '24 hours'
              AND a.created_at <  b.end_at
            ORDER BY a.theme_relevance_score DESC, a.id
            LIMIT :limit
            """, nativeQuery = true)
    List<RepresentArticleProjection> findRepresentArticlesByCountry(
            @Param("countryCode") String countryCode, @Param("limit") int limit);
}
