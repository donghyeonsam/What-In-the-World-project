package com.ssafy.witw.analysis.repository;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

@Repository
@RequiredArgsConstructor
public class IssueCountryAnalysisTargetRepository {

    private static final String FIND_TARGETS = """
            WITH bounds AS (
                SELECT CAST(? AS timestamp) AS period_start,
                       CAST(? AS timestamp) AS period_end
            ),
            top_issues AS (
                SELECT a.issue_id,
                       COUNT(*) AS issue_article_count
                FROM article a
                CROSS JOIN bounds b
                WHERE a.deleted_at IS NULL
                  AND a.issue_id IS NOT NULL
                  AND a.published_at >= b.period_start
                  AND a.published_at < b.period_end
                GROUP BY a.issue_id
                ORDER BY issue_article_count DESC, a.issue_id ASC
                LIMIT ?
            )
            SELECT t.issue_id,
                   a.publisher_country_code AS country_code,
                   COUNT(*) AS article_count
            FROM top_issues t
            JOIN article a ON a.issue_id = t.issue_id
            CROSS JOIN bounds b
            WHERE a.deleted_at IS NULL
              AND a.published_at >= b.period_start
              AND a.published_at < b.period_end
            GROUP BY t.issue_id, t.issue_article_count, a.publisher_country_code
            HAVING COUNT(*) >= ?
            ORDER BY t.issue_article_count DESC, t.issue_id ASC,
                     article_count DESC, a.publisher_country_code ASC
            """;

    private final JdbcTemplate jdbcTemplate;

    public List<Target> findTargets(
            LocalDateTime periodStart,
            LocalDateTime periodEnd,
            int topIssueLimit,
            int minCountryArticleCount
    ) {
        return jdbcTemplate.query(
                FIND_TARGETS,
                (resultSet, rowNum) -> new Target(
                        resultSet.getLong("issue_id"),
                        resultSet.getString("country_code"),
                        resultSet.getLong("article_count")
                ),
                Timestamp.valueOf(periodStart),
                Timestamp.valueOf(periodEnd),
                topIssueLimit,
                minCountryArticleCount
        );
    }

    public record Target(long issueId, String countryCode, long articleCount) {
    }
}
