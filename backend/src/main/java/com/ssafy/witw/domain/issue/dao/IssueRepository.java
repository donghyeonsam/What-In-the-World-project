package com.ssafy.witw.domain.issue.dao;

import com.ssafy.witw.domain.issue.dto.IssueInfo;
import com.ssafy.witw.domain.issue.entity.Issue;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface IssueRepository extends JpaRepository<Issue, Long> {

    @Query(value = """
            SELECT 
                i.name AS issueTitle,
                t.name AS themeTitle,
                COUNT(a.id) AS articleCount
            FROM issue i
            JOIN theme t ON i.theme_id = t.id 
            LEFT JOIN article a 
                ON i.id = a.issue_id
                AND a.deleted_at IS NULL            
            WHERE i.id = :issueId
            GROUP BY i.id, i.name, t.name
""", nativeQuery = true)
    IssuePreview getIssuePreviewByIssueId(@Param("issueId") Long issueId);

    interface IssuePreview{
        String getIssueTitle();
        Long getArticleCount();
        String getThemeTitle();
    }

    @Query(value = """
            SELECT i.id AS issueId, i.name AS issueTitle
            FROM issue i
            JOIN article a ON a.issue_id = i.id
            WHERE i.theme_id = :themeId
                AND a.deleted_at IS NULL
            GROUP BY i.id, i.name
            ORDER BY count(*) DESC, i.id ASC
            LIMIT :limit
""", nativeQuery = true)
    List<PrimaryIssue> getPrimaryIssuesByThemeId(@Param("themeId") Long themeId,@Param("limit") int limit);

    interface PrimaryIssue {
        Long getIssueId();
        String getIssueTitle();
    }

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

    // 최근 24시간 기사 수 기준 상위 이슈 랭킹 (이슈 단위)
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
            ORDER BY ti.article_count DESC, i.id
            """, nativeQuery = true)
    List<GlobalIssueRankRow> findGlobalIssueRankLast24Hours(@Param("limit") int limit);

    // LEFT JOIN 이라 기사가 0건인 이슈도 집계 0으로 행이 나오고, 이슈가 없을 때만 null 이 된다.
    // 삭제 조건은 ON 절에 둔다. WHERE 로 옮기면 삭제된 기사만 있는 이슈가 행 자체를 잃는다.
    @Query(value = """
        SELECT  i.id AS "issueId",
                i.name AS "issueName",
                count(a.id) AS "articleCount",
                count(distinct a.publisher_country_code) AS "countryCount"
        FROM issue i
        LEFT JOIN article a
            ON a.issue_id = i.id
            AND a.deleted_at IS NULL
        WHERE i.id = :issueId
        GROUP BY i.id, i.name
""", nativeQuery = true)
    IssueInfo findIssueById(@Param("issueId") long issueId);

    // 이슈 하나의 최근 24시간 국가별 톤
    @Query(value = """
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
            WHERE a.issue_id = :issueId
              AND a.deleted_at IS NULL
              AND a.published_at >= b.end_at - INTERVAL '24 hours'
              AND a.published_at < b.end_at
            GROUP BY c.country_code, c.name_ko, c.longitude, c.latitude
            ORDER BY AVG(a.tone_score) DESC, c.country_code
            """, nativeQuery = true)
    List<CountryToneRow> findCountryTonesLast24Hours(@Param("issueId") long issueId);

    interface GlobalIssueRankRow {
        long getIssueId();
        String getFieldName();
        String getThemeName();
        String getIssueName();
        long getArticleCount();
        LocalDateTime getFirstSeenAt();
    }
    interface CountryToneRow {
        String getCountryCode();
        String getCountryName();
        double getLongitude();
        double getLatitude();
        double getToneAvg();
        double getToneMax();
        double getToneMin();
        double getToneSd();
        long getArticleCount();
    }
}
