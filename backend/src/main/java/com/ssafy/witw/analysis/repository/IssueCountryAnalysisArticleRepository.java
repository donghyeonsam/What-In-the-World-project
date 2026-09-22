package com.ssafy.witw.analysis.repository;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

@Repository
@RequiredArgsConstructor
public class IssueCountryAnalysisArticleRepository {

    private static final String FIND_ARTICLES = """
            WITH bounds AS (
                SELECT CAST(? AS timestamp) AS period_start,
                       CAST(? AS timestamp) AS period_end
            )
            SELECT a.id,
                   COALESCE(NULLIF(BTRIM(a.translated_title), ''), a.original_title) AS title,
                   a.summary,
                   a.tone_score,
                   a.publisher,
                   a.published_at,
                   a.issue_similarity
            FROM article a
            JOIN issue i ON i.id = a.issue_id
            CROSS JOIN bounds b
            WHERE a.issue_id = ?
              AND a.publisher_country_code = ?
              AND i.created_at <= b.period_end
              AND (a.deleted_at IS NULL OR a.deleted_at > b.period_end)
              AND a.issue_assigned_at <= b.period_end
              AND a.created_at <= b.period_end
              AND a.published_at >= b.period_start
              AND a.published_at < b.period_end
            ORDER BY a.published_at DESC, a.id ASC
            """;

    private final JdbcTemplate jdbcTemplate;

    public List<ArticleForAnalysis> findArticles(
            long issueId,
            String countryCode,
            LocalDateTime periodStart,
            LocalDateTime periodEnd
    ) {
        return jdbcTemplate.query(
                FIND_ARTICLES,
                (resultSet, rowNum) -> new ArticleForAnalysis(
                        resultSet.getString("id"),
                        resultSet.getString("title"),
                        resultSet.getString("summary"),
                        resultSet.getBigDecimal("tone_score"),
                        resultSet.getString("publisher"),
                        resultSet.getTimestamp("published_at").toLocalDateTime(),
                        resultSet.getBigDecimal("issue_similarity")
                ),
                Timestamp.valueOf(periodStart),
                Timestamp.valueOf(periodEnd),
                issueId,
                countryCode
        );
    }

    public record ArticleForAnalysis(
            String articleId,
            String title,
            String summary,
            BigDecimal toneScore,
            String publisher,
            LocalDateTime publishedAt,
            BigDecimal issueSimilarity
    ) {
    }
}
