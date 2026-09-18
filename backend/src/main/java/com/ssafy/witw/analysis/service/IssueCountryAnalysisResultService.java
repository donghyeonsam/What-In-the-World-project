package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisResultRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;

/**
 * 국가별 이슈 분석 결과를 DB에 저장하는 Service.
 *
 * 하나의 분석 작업에서 다음 두 저장을 하나의 트랜잭션으로 처리한다.
 *
 * 1. issue_country_analysis
 *    - GMS 분석 결과 저장
 *
 * 2. issue_country_analysis_evidence
 *    - GMS에 실제 전달했던 대표 기사 전체 저장
 *
 * 두 번째 저장 중 문제가 발생하면
 * 첫 번째 분석 결과 저장도 함께 Rollback 된다.
 */
@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisResultService {

    private final IssueCountryAnalysisResultRepository resultRepository;
    private final ObjectMapper objectMapper;

    /**
     * 검증이 완료된 국가별 이슈 분석 결과를 저장한다.
     *
     * @param target                   분석 대상 이슈 × 국가 정보
     * @param createdAt                Scheduler에서 정한 분석 기준 시각
     * @param result                   검증이 완료된 GMS 분석 결과
     * @param representativeArticleIds GMS에 전달했던 대표 기사 ID 전체
     * @return 생성된 issue_country_analysis.id
     */
    @Transactional
    public long save(
            Target target,
            LocalDateTime createdAt,
            AnalysisResult result,
            List<String> representativeArticleIds
    ) {
        Objects.requireNonNull(
                target,
                "target"
        );

        Objects.requireNonNull(
                createdAt,
                "createdAt"
        );

        Objects.requireNonNull(
                result,
                "result"
        );

        Objects.requireNonNull(
                representativeArticleIds,
                "representativeArticleIds"
        );

        if (representativeArticleIds.isEmpty()) {
            throw new IllegalArgumentException(
                    "Representative article IDs must not be empty"
            );
        }

        /*
         * AnalysisResult.details는 List<String>이지만
         * 현재 DB의 details 컬럼은 TEXT이므로
         * JSON 문자열 형태로 직렬화해서 저장한다.
         *
         * 예:
         *
         * [
         *   "미국 기업에 미칠 영향을 비중 있게 다룬다.",
         *   "안보 측면에서 규제 필요성을 강조한다."
         * ]
         */
        String detailsJson =
                objectMapper.writeValueAsString(
                        result.details()
                );

        /*
         * 혹시 동일 articleId가 중복으로 전달되는 경우를 막는다.
         *
         * PromptService에서는 정상적으로 중복되지 않지만,
         * DB 관계 테이블에 같은 evidence를 두 번 저장하지 않도록
         * 마지막 방어선으로 한 번 더 정리한다.
         */
        List<String> evidenceArticleIds =
                representativeArticleIds.stream()
                        .filter(articleId ->
                                articleId != null
                                        && !articleId.isBlank()
                        )
                        .map(String::strip)
                        .distinct()
                        .toList();

        if (evidenceArticleIds.isEmpty()) {
            throw new IllegalArgumentException(
                    "No valid representative article IDs"
            );
        }

        /*
         * 1. 국가별 이슈 분석 결과 저장
         *
         * INSERT ... RETURNING id를 통해
         * 새로 생성된 analysisId를 받는다.
         */
        long analysisId =
                resultRepository.insertAnalysis(
                        target.issueId(),
                        target.countryCode(),
                        result.title(),
                        result.summary(),
                        detailsJson,
                        target.articleCount(),
                        createdAt
                );

        /*
         * 2. 해당 분석에 사용했던 대표 기사 전체 연결
         *
         * analysisId 하나에 여러 articleId가 연결된다.
         */
        resultRepository.insertEvidence(
                analysisId,
                evidenceArticleIds
        );

        return analysisId;
    }
}