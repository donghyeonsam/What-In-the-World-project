package com.ssafy.witw.domain.article.dao;

import com.ssafy.witw.domain.article.entity.Article;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

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
}
