package com.ssafy.witw.analysis.repository;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 국가별 이슈 분석 결과와 분석에 사용한 대표 기사들을 DB에 저장한다.
 *
 * 실제 트랜잭션 제어는 Service 계층에서 담당하고,
 * Repository는 SQL 실행만 담당한다.
 */
@Repository
@RequiredArgsConstructor
public class IssueCountryAnalysisResultRepository {

    /**
     * GMS가 생성한 국가별 이슈 분석 결과를 저장한다.
     *
     * PostgreSQL의 RETURNING id를 사용하여
     * 새로 생성된 analysis_id를 바로 반환한다.
     */
    private static final String INSERT_ANALYSIS = """
            INSERT INTO issue_country_analysis (
                issue_id,
                country_code,
                title,
                summary,
                details,
                article_count,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """;

    /**
     * 하나의 분석 결과와 실제 분석에 사용한 대표 기사를 연결한다.
     *
     * 하나의 analysis_id에 여러 article_id가 연결되는 1:N 구조다.
     */
    private static final String INSERT_EVIDENCE = """
            INSERT INTO issue_country_analysis_evidence (
                analysis_id,
                article_id
            )
            VALUES (?, ?)
            """;

    private final JdbcTemplate jdbcTemplate;

    /**
     * 국가별 이슈 분석 결과를 저장하고 생성된 PK를 반환한다.
     *
     * @param issueId      분석 대상 이슈 ID
     * @param countryCode  분석 대상 국가 코드
     * @param title        GMS가 생성한 분석 제목
     * @param summary      GMS가 생성한 전체 보도 경향 요약
     * @param details      GMS details 배열을 JSON 문자열로 직렬화한 값
     * @param articleCount 해당 이슈 × 국가의 전체 기사 수
     * @param createdAt    Scheduler가 분석 시작 시 정한 기준 시각
     * @return 생성된 issue_country_analysis.id
     */
    public long insertAnalysis(
            long issueId,
            String countryCode,
            String title,
            String summary,
            String details,
            long articleCount,
            LocalDateTime createdAt
    ) {
        Long analysisId = jdbcTemplate.queryForObject(
                INSERT_ANALYSIS,
                Long.class,
                issueId,
                countryCode,
                title,
                summary,
                details,
                articleCount,
                Timestamp.valueOf(createdAt)
        );

        if (analysisId == null) {
            throw new IllegalStateException(
                    "Failed to obtain generated issue_country_analysis id"
            );
        }

        return analysisId;
    }

    /**
     * 분석에 실제 전달된 대표 기사 전체를
     * issue_country_analysis_evidence에 일괄 저장한다.
     *
     * GMS가 기사 ID를 반환하는 것이 아니라,
     * PromptService가 보관하고 있던 representativeArticleIds를 사용한다.
     */
    public void insertEvidence(
            long analysisId,
            List<String> articleIds
    ) {
        if (articleIds == null || articleIds.isEmpty()) {
            return;
        }

        jdbcTemplate.batchUpdate(
                INSERT_EVIDENCE,
                articleIds,
                articleIds.size(),
                (preparedStatement, articleId) -> {
                    preparedStatement.setLong(
                            1,
                            analysisId
                    );

                    preparedStatement.setString(
                            2,
                            articleId
                    );
                }
        );
    }
}