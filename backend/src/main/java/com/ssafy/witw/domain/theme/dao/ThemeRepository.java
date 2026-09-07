package com.ssafy.witw.domain.theme.dao;

import com.ssafy.witw.domain.theme.entity.Theme;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface ThemeRepository extends JpaRepository<Theme, Long> {

    // TODO: article (country, published_at, theme_id) 복합 인덱스 검토
    @Query(value = """
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
                WHERE a.publisher_country_code = :countryCode
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
                LIMIT :limit
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
            ORDER BY p.article_count_24 DESC, p.theme_id, b.bucket_start
            """, nativeQuery = true)
    List<PopularThemeTrendRow> findPopularThemesWithHourlyTrend(
            @Param("countryCode") String countryCode,
            @Param("limit") int limit
    );

    // 시간 버킷 정렬이 필요 없으므로 다른 24시간 쿼리들과 같은 기준 시각을 사용
    @Query(value = """
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
        WHERE a.publisher_country_code = :countryCode
          AND a.published_at >= b.end_at - INTERVAL '24 hours'
          AND a.published_at <  b.end_at
          AND a.deleted_at IS NULL
        GROUP BY t.id, f.name, t.name
        ORDER BY COUNT(*) DESC, t.id
        LIMIT :limit
        """, nativeQuery = true)
    List<PopularThemeRow> findPopularThemes(
            @Param("countryCode") String countryCode, @Param("limit") int limit);

    interface PopularThemeRow {
        long getThemeId();
        String getFieldName();
        String getThemeName();
        long getArticleCount24();
    }

    interface PopularThemeTrendRow extends PopularThemeRow {
        LocalDateTime getBucketStart();
        long getArticleCount();
    }
}
