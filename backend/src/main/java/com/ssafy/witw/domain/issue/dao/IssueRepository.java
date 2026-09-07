package com.ssafy.witw.domain.issue.dao;

import com.ssafy.witw.domain.issue.entity.Issue;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface IssueRepository extends JpaRepository<Issue, Long> {

    // 이슈가 속한 테마·필드 조회
    @Query(value = """
            SELECT i.id   AS "issueId",
                   i.name AS "issueName",
                   t.name AS "themeName",
                   f.name AS "fieldName"
            FROM issue i
            JOIN theme t ON t.id = i.theme_id
            JOIN field f ON f.id = t.field_id
            WHERE i.id IN (:issueIds)
            """, nativeQuery = true)
    List<IssueDetailRow> findIssueDetailsByIds(@Param("issueIds") List<Long> issueIds);

    // TODO: article (issue_id, publisher_country_code, deleted_at) 복합 인덱스 검토
    @Query(value = """
            SELECT i.id           AS "issueId",
                   i.name         AS "issueName",
                   t.name         AS "themeName",
                   f.name         AS "fieldName",
                   c.country_code AS "countryCode",
                   c.name_ko      AS "countryName"
            FROM issue i
            JOIN theme t ON t.id = i.theme_id
            JOIN field f ON f.id = t.field_id
            JOIN country c ON c.country_code = :countryCode
            WHERE i.id = :issueId
              AND EXISTS (
                  SELECT 1
                  FROM article a
                  WHERE a.issue_id = i.id
                    AND a.publisher_country_code = c.country_code
                    AND a.deleted_at IS NULL
              )
            """, nativeQuery = true)
    Optional<CountryIssueDetailRow> findCountryIssueDetail(
            @Param("issueId") Long issueId,
            @Param("countryCode") String countryCode
    );

    interface IssueDetailRow {
        long getIssueId();
        String getIssueName();
        String getThemeName();
        String getFieldName();
    }

    interface CountryIssueDetailRow {
        long getIssueId();
        String getIssueName();
        String getThemeName();
        String getFieldName();
        String getCountryCode();
        String getCountryName();
    }

    // 최근 24시간 기사 수 기준 상위 이슈 랭킹 + 이슈별 국가 톤 (이슈 x 국가 단위로 flat 하게 반환)
    // TODO: article (deleted_at, published_at, issue_id) 복합 인덱스 검토
    @Query(value = """
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
                LIMIT :limit
            ),
            country_tones AS (
                SELECT a.issue_id                            AS issue_id,
                       a.publisher_country_code              AS country_code,
                       AVG(a.tone_score)::double precision   AS tone_avg,
                       MAX(a.tone_score)::double precision   AS tone_max,
                       MIN(a.tone_score)::double precision   AS tone_min
                FROM article a
                JOIN top_issues ti ON ti.issue_id = a.issue_id
                CROSS JOIN bounds b
                WHERE a.deleted_at IS NULL
                  AND a.published_at >= b.end_at - INTERVAL '24 hours'
                  AND a.published_at < b.end_at
                GROUP BY a.issue_id, a.publisher_country_code
            )
            SELECT i.id             AS "issueId",
                   f.name           AS "fieldName",
                   t.name           AS "themeName",
                   i.name           AS "issueName",
                   ti.article_count AS "articleCount",
                   i.first_seen_at  AS "firstSeenAt",
                   c.country_code   AS "countryCode",
                   c.name_ko        AS "countryName",
                   c.longitude      AS "longitude",
                   c.latitude       AS "latitude",
                   ct.tone_avg      AS "toneAvg",
                   ct.tone_max      AS "toneMax",
                   ct.tone_min      AS "toneMin"
            FROM top_issues ti
            JOIN issue i ON i.id = ti.issue_id
            JOIN theme t ON t.id = i.theme_id
            JOIN field f ON f.id = t.field_id
            JOIN country_tones ct ON ct.issue_id = ti.issue_id
            JOIN country c ON c.country_code = ct.country_code
            ORDER BY ti.article_count DESC, i.id, ct.tone_avg DESC, c.country_code
            """, nativeQuery = true)
    List<GlobalIssueRankRow> findGlobalIssueRankLast24Hours(@Param("limit") int limit);

    interface GlobalIssueRankRow {
        long getIssueId();
        String getFieldName();
        String getThemeName();
        String getIssueName();
        long getArticleCount();
        LocalDateTime getFirstSeenAt();
        String getCountryCode();
        String getCountryName();
        double getLongitude();
        double getLatitude();
        double getToneAvg();
        double getToneMax();
        double getToneMin();
    }

}
