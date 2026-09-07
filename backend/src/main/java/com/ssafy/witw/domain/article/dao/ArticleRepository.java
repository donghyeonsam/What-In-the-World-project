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
            ORDER BY a.issue_similarity DESC, a.id ASC
            LIMIT :limit
            """, nativeQuery = true)
    List<RepresentArticleProjection> getRepresentArticlesByIssueId(
            @Param("issueId") Long issueId, @Param("limit") int limit);


}
