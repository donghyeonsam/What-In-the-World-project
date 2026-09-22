package com.ssafy.witw.domain.issue.dao;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;

@Repository
@RequiredArgsConstructor
public class IssueHeatScoreStore {

    private static final String INSERT_COUNTRY_SCORES = """
            WITH bounds AS (
                SELECT CAST(? AS timestamp) AS end_at
            ),
            current_articles AS (
                SELECT a.issue_id,
                       a.publisher_country_code AS country_code,
                       CASE
                           WHEN NULLIF(BTRIM(a.publisher), '') IS NULL
                             OR BTRIM(a.publisher) = '정보없음' THEN NULL
                           ELSE LOWER(BTRIM(a.publisher))
                       END AS publisher_key,
                       a.published_at
                FROM article a
                CROSS JOIN bounds b
                WHERE a.deleted_at IS NULL
                  AND a.published_at >= b.end_at - INTERVAL '24 hours'
                  AND a.published_at < b.end_at
            ),
            country_current AS (
                SELECT country_code,
                       COUNT(*) AS article_count,
                       COUNT(DISTINCT publisher_key) AS active_publishers
                FROM current_articles
                GROUP BY country_code
            ),
            issue_country AS (
                SELECT issue_id,
                       country_code,
                       COUNT(*) AS article_count,
                       COUNT(*) FILTER (
                           WHERE published_at >= (SELECT end_at FROM bounds) - INTERVAL '3 hours'
                       ) AS article_count_3h,
                       COUNT(DISTINCT publisher_key) AS publisher_count
                FROM current_articles
                WHERE issue_id IS NOT NULL
                GROUP BY issue_id, country_code
            ),
            issue_publisher_counts AS (
                SELECT issue_id, country_code, publisher_key, COUNT(*) AS article_count
                FROM current_articles
                WHERE issue_id IS NOT NULL
                  AND publisher_key IS NOT NULL
                GROUP BY issue_id, country_code, publisher_key
            ),
            issue_diversity AS (
                SELECT issue_id,
                       country_code,
                       CASE WHEN SUM(article_count) = 0 THEN 0.0
                            ELSE 100.0 * (1.0 -
                                SUM(article_count * article_count)::double precision
                                / POWER(SUM(article_count)::double precision, 2))
                       END AS diversity_score
                FROM issue_publisher_counts
                GROUP BY issue_id, country_code
            ),
            issue_metrics AS (
                SELECT ic.*,
                       cc.article_count AS country_article_count,
                       cc.active_publishers,
                       COALESCE(id.diversity_score, 0.0) AS diversity_score,
                       ic.article_count::double precision
                           / NULLIF(cc.article_count, 0) AS news_share,
                       (ic.article_count_3h + 1.0)
                           / ((ic.article_count - ic.article_count_3h) / 7.0 + 1.0)
                           AS momentum_ratio
                FROM issue_country ic
                JOIN country_current cc USING (country_code)
                LEFT JOIN issue_diversity id USING (issue_id, country_code)
            ),
            relative_metrics AS (
                SELECT im.*,
                       100.0 * CUME_DIST() OVER (
                           PARTITION BY country_code ORDER BY news_share
                       ) AS news_share_score,
                       100.0 * CUME_DIST() OVER (
                           PARTITION BY country_code ORDER BY momentum_ratio
                       ) AS momentum_score,
                        100.0 * SQRT(
                            LEAST(1.0, publisher_count::double precision
                                / GREATEST(active_publishers, 1))
                        ) AS publisher_coverage_score
                FROM issue_metrics im
            ),
            scored AS (
                SELECT rm.*,
                       LEAST(1.0,
                           SQRT(
                               (1.0 - EXP(-article_count / 3.0))
                                * GREATEST(
                                    1.0 - EXP(-publisher_count / 2.0),
                                    0.35 * (1.0 - EXP(-article_count / 3.0))
                                )
                            )
                        ) AS confidence
                FROM relative_metrics rm
            )
            INSERT INTO issue_country_heat_score (
                issue_id, country_code, calculated_at, score_version, local_heat_score
            )
            SELECT issue_id,
                   country_code,
                   (SELECT end_at FROM bounds),
                   'hierarchical-v1',
                   ROUND(CAST((
                       0.35 * news_share_score
                       + 0.30 * momentum_score
                       + 0.20 * publisher_coverage_score
                       + 0.15 * diversity_score
                   ) * confidence AS numeric), 2)
            FROM scored
            """;

    private static final String INSERT_GLOBAL_SCORES = """
            WITH bounds AS (
                SELECT CAST(? AS timestamp) AS end_at
            ),
            ranked_countries AS (
                SELECT s.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY issue_id
                           ORDER BY local_heat_score DESC, country_code
                       ) AS country_rank
                FROM issue_country_heat_score s
                CROSS JOIN bounds b
                WHERE s.calculated_at = b.end_at
            ),
            issue_rollup AS (
                SELECT issue_id,
                       COUNT(*) AS country_count,
                       AVG(local_heat_score) FILTER (WHERE country_rank <= 5)
                           AS local_strength_score
                FROM ranked_countries
                GROUP BY issue_id
            ),
            components AS (
                SELECT ir.*,
                       100.0 * LEAST(1.0,
                           LN(1.0 + ir.country_count) / LN(11.0)
                       ) AS country_breadth_score
                FROM issue_rollup ir
            )
            INSERT INTO issue_global_heat_score (
                issue_id, calculated_at, score_version, global_heat_score, country_count
            )
            SELECT issue_id,
                   (SELECT end_at FROM bounds),
                   'hierarchical-v1',
                   ROUND(CAST(
                       0.60 * local_strength_score
                       + 0.40 * country_breadth_score
                   AS numeric), 2),
                   country_count
            FROM components
            """;

    private final JdbcTemplate jdbcTemplate;

    public int appendCountryScores(LocalDateTime calculatedAt) {
        return jdbcTemplate.update(INSERT_COUNTRY_SCORES, calculatedAt);
    }

    public int appendGlobalScores(LocalDateTime calculatedAt) {
        return jdbcTemplate.update(INSERT_GLOBAL_SCORES, calculatedAt);
    }
}
