package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisArticleRepository.ArticleForAnalysis;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisQueryRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisGmsService.GmsAnalysisException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.InsufficientArticlesException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.InvalidAnalysisResponseException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 하나의 "이슈 × 국가" 분석 작업을 비동기로 수행하는 Worker.
 *
 * 처리 순서:
 * 1. 분석 대상 기사 조회
 * 2. 대표 기사 선정 및 GMS 프롬프트 생성
 * 3. GMS LLM 분석 요청
 * 4. GMS 응답 검증
 * 5. 분석 결과와 대표 기사 ID를 DB에 저장
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisWorkerService {

    private final IssueCountryAnalysisArticleService articleService;
    private final IssueCountryAnalysisQueryRepository analysisQueryRepository;
    private final IssueCountryAnalysisPromptService promptService;
    private final IssueCountryAnalysisGmsService gmsService;
    private final IssueCountryAnalysisResponseValidator responseValidator;
    private final IssueCountryAnalysisResultService resultService;

    /**
     * 하나의 이슈 × 국가 분석 작업을 비동기로 수행한다.
     *
     * issueCountryAnalysisExecutor 전용 Thread Pool에서 실행된다.
     *
     * 현재 Worker 수는 AsyncConfig 설정에 따라 결정되며,
     * pool-size를 늘리면 동일한 코드로 여러 분석 작업을 병렬 처리할 수 있다.
     */
    @Async("issueCountryAnalysisExecutor")
    public void analyze(
            Target target,
            LocalDateTime periodStart,
            LocalDateTime periodEnd
    ) {
        long issueId = target.issueId();
        String issueName = target.issueName();
        String countryCode = target.countryCode();
        String countryName = target.countryName();

        log.info(
                "국가별 이슈 분석 시작: "
                        + "issueId={}, issueName={}, "
                        + "countryCode={}, countryName={}, "
                        + "articleCount={}, periodStart={}, periodEnd={}",
                issueId,
                issueName,
                countryCode,
                countryName,
                target.articleCount(),
                periodStart,
                periodEnd
        );

        try {
            /*
             * 1. 해당 이슈 × 국가 × 기간에 속하는 기사들을 조회한다.
             */
            List<ArticleForAnalysis> articles =
                    articleService.findArticles(
                            issueId,
                            countryCode,
                            periodStart,
                            periodEnd
                    );

            log.debug(
                    "분석용 기사 조회 완료: "
                            + "issueId={}, countryCode={}, articleCount={}",
                    issueId,
                    countryCode,
                    articles.size()
            );

            /*
             * 2. GMS 분석용 대표 기사를 선정하고 Prompt를 생성한다.
             *
             * PromptService 내부에서:
             * - 재분석에서는 summary / toneScore 없는 기사 제외
             * - 제목 중복 제거
             * - 최소 분석 가능 기사 수 확인
             * - 언론사 / 논조 / 시간대 다양성 고려
             * - 대표 기사 최대 12개 선정
             *
             * 대표 기사 ID는 GMS로 전달하지 않고
             * PreparedPrompt 내부에 별도로 보관한다.
             */
            boolean hasPreviousAnalysis = analysisQueryRepository.analysisExistsAt(issueId, countryCode, periodEnd);
            PreparedPrompt prompt =
                    (hasPreviousAnalysis ? promptService.prepare(
                            issueId,
                            issueName,
                            countryCode,
                            countryName,
                            target.articleCount(),
                            periodStart,
                            periodEnd,
                            articles
                    ) : promptService.prepareInitial(
                            issueId,
                            issueName,
                            countryCode,
                            countryName,
                            target.articleCount(),
                            periodStart,
                            periodEnd,
                            articles
                    ));

            log.debug(
                    "GMS Prompt 생성 완료: "
                            + "issueId={}, countryCode={}, "
                            + "usableArticleCount={}, "
                            + "representativeArticleCount={}",
                    issueId,
                    countryCode,
                    prompt.usableArticleCount(),
                    prompt.representativeArticleIds().size()
            );

            /*
             * 3. GMS LLM에 분석 요청.
             *
             * 기대 응답:
             *
             * {
             *   "title": "...",
             *   "summary": "...",
             *   "details": [...]
             * }
             */
            String responseText =
                    gmsService.analyze(prompt);

            /*
             * 4. GMS가 반환한 JSON 구조와 값을 검증한다.
             */
            AnalysisResult result =
                    responseValidator.validate(responseText);

            // Scheduler가 정한 기준 시각과 실제 사용한 대표 기사 전체를 함께 저장한다.
            long analysisId = resultService.save(
                    target,
                    periodEnd,
                    result,
                    prompt.representativeArticleIds()
            );

            log.info(
                    "국가별 이슈 분석 완료: "
                            + "issueId={}, countryCode={}, "
                            + "analysisId={}, title={}, representativeArticleCount={}",
                    issueId,
                    countryCode,
                    analysisId,
                    result.title(),
                    prompt.representativeArticleIds().size()
            );

            log.debug(
                    "국가별 이슈 분석 결과: "
                            + "issueId={}, countryCode={}, "
                            + "summary={}, details={}, "
                            + "representativeArticleIds={}",
                    issueId,
                    countryCode,
                    result.summary(),
                    result.details(),
                    prompt.representativeArticleIds()
            );

        } catch (InsufficientArticlesException exception) {

            /*
             * 첫 분석은 제목이 있는 기사가 한 건도 없으면,
             * 재분석은 요약 누락 또는 제목 중복 제거 후
             * 실제 사용할 수 있는 기사가 5개 미만이면 건너뛴다.
             *
             * 이 경우 시스템 장애가 아니므로 해당 Target만 건너뛴다.
             */
            log.warn(
                    "국가별 이슈 분석 건너뜀 - 분석 가능한 기사 부족: "
                            + "issueId={}, countryCode={}, reason={}",
                    issueId,
                    countryCode,
                    exception.getMessage()
            );

        } catch (GmsAnalysisException exception) {

            /*
             * GMS timeout, 네트워크 오류, API 오류 등.
             */
            log.error(
                    "국가별 이슈 분석 실패 - GMS 호출 오류: "
                            + "issueId={}, countryCode={}",
                    issueId,
                    countryCode,
                    exception
            );

        } catch (InvalidAnalysisResponseException exception) {

            /*
             * GMS 호출은 성공했지만
             * 반환된 JSON이 우리가 정한 형식을 만족하지 않는 경우.
             */
            log.error(
                    "국가별 이슈 분석 실패 - GMS 응답 검증 오류: "
                            + "issueId={}, countryCode={}",
                    issueId,
                    countryCode,
                    exception
            );

        } catch (Exception exception) {

            /*
             * 하나의 Target에서 발생한 예상하지 못한 오류가
             * 다른 비동기 분석 작업에 영향을 주지 않도록 처리한다.
             */
            log.error(
                    "국가별 이슈 분석 중 예상하지 못한 오류 발생: "
                            + "issueId={}, countryCode={}",
                    issueId,
                    countryCode,
                    exception
            );
        }
    }
}
