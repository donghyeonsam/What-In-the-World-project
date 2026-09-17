package com.ssafy.witw.domain.country.dao;

import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.country.entity.Country;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface CountryRepository extends JpaRepository<Country, String> {

    // 최근 24시간, 해당 국가가 발행한 기사가 언급한 국가들의 비율 (자기 자신 제외)
    // TODO: article_country_mention (article_id) 인덱스 검토
    @Query(value = """
            WITH bounds AS (
                SELECT CAST(:asOf AS timestamp) AS end_at
            ),
            mention_counts AS (
                SELECT m.country_code AS country_code,
                       COUNT(*)       AS mention_count
                FROM article a
                JOIN article_country_mention m ON m.article_id = a.id
                CROSS JOIN bounds b
                WHERE a.publisher_country_code = :countryCode
                  AND m.country_code <> :countryCode
                  AND (a.deleted_at IS NULL OR a.deleted_at > :asOf)
                  AND a.created_at <= :asOf
                  AND a.published_at < :asOf
                  AND a.published_at >= b.end_at - INTERVAL '24 hours'
                  AND a.published_at <  b.end_at
                GROUP BY m.country_code
            )
            SELECT c.country_code AS "countryCode",
                   c.name_ko      AS "countryName",
                   mc.mention_count::double precision
                       / SUM(mc.mention_count) OVER () AS "mentionRatio"
            FROM mention_counts mc
            JOIN country c ON c.country_code = mc.country_code
            ORDER BY mc.mention_count DESC, c.country_code
            LIMIT :limit
            """, nativeQuery = true)
    List<MentionRatioRow> findOutgoingMentionRatios(@Param("countryCode") String countryCode, @Param("limit") int limit, @Param("asOf") LocalDateTime asOf);

    default List<MentionRatioRow> findOutgoingMentionRatios(String countryCode, int limit) {
        return findOutgoingMentionRatios(countryCode, limit, QueryTime.now());
    }

    // 최근 24시간, 해당 국가를 언급한 기사들의 발행국 비율 (자기 자신 제외)
    // TODO: article_country_mention (country_code) 인덱스 검토
    @Query(value = """
            WITH bounds AS (
                SELECT CAST(:asOf AS timestamp) AS end_at
            ),
            mention_counts AS (
                SELECT a.publisher_country_code AS country_code,
                       COUNT(*)                 AS mention_count
                FROM article_country_mention m
                JOIN article a ON a.id = m.article_id
                CROSS JOIN bounds b
                WHERE m.country_code = :countryCode
                  AND a.publisher_country_code <> :countryCode
                  AND (a.deleted_at IS NULL OR a.deleted_at > :asOf)
                  AND a.created_at <= :asOf
                  AND a.published_at < :asOf
                  AND a.published_at >= b.end_at - INTERVAL '24 hours'
                  AND a.published_at <  b.end_at
                GROUP BY a.publisher_country_code
            )
            SELECT c.country_code AS "countryCode",
                   c.name_ko      AS "countryName",
                   mc.mention_count::double precision
                       / SUM(mc.mention_count) OVER () AS "mentionRatio"
            FROM mention_counts mc
            JOIN country c ON c.country_code = mc.country_code
            ORDER BY mc.mention_count DESC, c.country_code
            LIMIT :limit
            """, nativeQuery = true)
    List<MentionRatioRow> findIncomingMentionRatios(@Param("countryCode") String countryCode, @Param("limit") int limit, @Param("asOf") LocalDateTime asOf);

    default List<MentionRatioRow> findIncomingMentionRatios(String countryCode, int limit) {
        return findIncomingMentionRatios(countryCode, limit, QueryTime.now());
    }

    interface MentionRatioRow {
        String getCountryCode();
        String getCountryName();
        double getMentionRatio();
    }
}
