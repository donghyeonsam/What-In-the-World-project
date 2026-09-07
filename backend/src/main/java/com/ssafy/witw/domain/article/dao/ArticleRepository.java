package com.ssafy.witw.domain.article.dao;

import com.ssafy.witw.domain.article.entity.Article;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

public interface ArticleRepository extends JpaRepository<Article, String> {

    // 전체 수집 기사 수
    long countByDeletedAtIsNull();

    // 최근 24시간 기사 수. countryCode / issueId 는 null 이면 해당 조건 제외
    // TODO: article (deleted_at, created_at, publisher_country_code, issue_id) 복합 인덱스 검토
    @Query(value = """
            SELECT COUNT(*)
            FROM article a
            WHERE a.deleted_at IS NULL
              AND a.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul') - INTERVAL '24 hours'
              AND (CAST(:countryCode AS TEXT) IS NULL
                   OR a.publisher_country_code = :countryCode)
              AND (CAST(:issueId AS BIGINT) IS NULL
                   OR a.issue_id = :issueId)
            """, nativeQuery = true)
    long countArticlesLast24Hours(
            @Param("countryCode") String countryCode,
            @Param("issueId") Long issueId
    );

//    // TODO: article (deleted_at, issue_id) 부분 인덱스 검토
//    @Query(value = """
//            SELECT a.issue_id AS "issueId",
//                   i.name     AS "issueName",
//                   COUNT(*)   AS "articleCount"
//            FROM article a
//            JOIN issue i ON i.id = a.issue_id
//            WHERE a.deleted_at IS NULL
//            GROUP BY a.issue_id, i.name
//            ORDER BY "articleCount" DESC, a.issue_id
//            LIMIT :limit
//            """, nativeQuery = true)
//    List<TopIssueRow> findTopIssuesByArticleCount(@Param("limit") int limit);
//
//    // TODO: article (publisher_country_code, created_at) 복합 인덱스 검토
//    @Query(value = """
//            WITH country_counts AS (
//                SELECT a.publisher_country_code AS country_code,
//                       COUNT(*) AS article_count,
//                       RANK() OVER (ORDER BY COUNT(*) DESC) AS article_rank
//                FROM article a
//                WHERE a.created_at >= (NOW() AT TIME ZONE 'Asia/Seoul') - INTERVAL '24 hours'
//                  AND a.deleted_at IS NULL
//                GROUP BY a.publisher_country_code
//            )
//            SELECT c.article_count AS "articleCount",
//                   c.article_rank  AS "articleRank"
//            FROM country_counts c
//            WHERE c.country_code = :countryCode
//            """, nativeQuery = true)
//    Optional<CountryArticleRankRow> findCountryArticleRankLast24Hours(@Param("countryCode") String countryCode);
//
//    interface TopIssueRow {
//        long getIssueId();
//        String getIssueName();
//        long getArticleCount();
//    }
//
//    interface CountryArticleRankRow {
//        long getArticleCount();
//        long getArticleRank();
//    }
}
