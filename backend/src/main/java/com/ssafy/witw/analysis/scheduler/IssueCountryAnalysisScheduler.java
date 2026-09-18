package com.ssafy.witw.analysis.scheduler;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisTargetService;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisWorkerService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

/**
 * 국가별 이슈 분석 작업을 주기적으로 시작하는 Scheduler.
 *
 * 역할:
 * 1. 분석 기준 시각과 최근 24시간 분석 기간을 결정한다.
 * 2. 분석 대상이 되는 이슈 × 국가 Target 목록을 조회한다.
 * 3. 각 Target을 비동기 Worker에 전달한다.
 *
 * 실제 기사 조회, GMS 분석, 결과 검증, DB 저장은
 * IssueCountryAnalysisWorkerService에서 수행한다.
 *
 * analysis.scheduler.enabled=false로 Scheduler를 비활성화할 수 있고,
 * analysis.scheduler.cron 설정으로 실행 주기를 변경할 수 있다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "analysis.scheduler",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class IssueCountryAnalysisScheduler {

    /**
     * 국가별 분석의 기준 시간대.
     *
     * 분석 기간 및 결과 created_at을 모두 동일한 시각 기준으로
     * 관리하기 위해 Asia/Seoul을 사용한다.
     */
    private static final ZoneId ANALYSIS_ZONE =
            ZoneId.of("Asia/Seoul");

    private final IssueCountryAnalysisTargetService targetService;
    private final IssueCountryAnalysisWorkerService workerService;

    /**
     * 국가별 이슈 분석을 주기적으로 실행한다.
     *
     * 기본값은 매시간 정각이다.
     *
     * 예:
     * 0 0 * * * *   -> 매시간
     * 0 0 *&#47;3 * * * -> 3시간마다
     */
    @Scheduled(
            cron = "${analysis.scheduler.cron:0 0 * * * *}",
            zone = "Asia/Seoul"
    )
    public void runAnalysis() {

        /*
         * Scheduler 실행 시점을 한 번만 생성한다.
         *
         * 이 값을:
         * - 분석 기간 종료 시각
         * - 최종 분석 결과 created_at
         *
         * 으로 동일하게 사용한다.
         */
        LocalDateTime createdAt =
                LocalDateTime.now(ANALYSIS_ZONE);

        /*
         * 현재 시각을 기준으로 최근 24시간의 기사를 분석한다.
         *
         * [periodStart, createdAt)
         */
        LocalDateTime periodStart =
                createdAt.minusHours(24);

        /*
         * 최근 24시간 기준으로:
         *
         * 1. 기사량이 많은 글로벌 이슈 TOP N을 선정하고
         * 2. 각 이슈에서 최소 기사 수 기준을 만족하는 국가를 찾는다.
         *
         * Target에는 다음 정보가 포함된다.
         *
         * - issueId
         * - issueName
         * - countryCode
         * - countryName
         * - articleCount
         */
        List<Target> targets =
                targetService.findTargets(
                        periodStart,
                        createdAt
                );

        log.info(
                "국가별 이슈 분석 대상 선정 완료: "
                        + "periodStart={}, createdAt={}, targetCount={}",
                periodStart,
                createdAt,
                targets.size()
        );

        /*
         * 선정된 Target 각각을 비동기 Worker에 전달한다.
         *
         * workerService.analyze()에는 @Async가 적용되어 있으므로
         * Scheduler Thread가 GMS 분석이 끝날 때까지 기다리지 않는다.
         *
         * 현재 Worker Pool이 1개라면:
         *
         * Target A -> 실행
         * Target B -> Queue 대기
         * Target C -> Queue 대기
         *
         * 형태로 순차 처리된다.
         *
         * 추후 pool-size를 2~3으로 늘리면
         * 이 코드를 수정하지 않고 병렬 처리할 수 있다.
         */
        int submittedCount = 0;
        for (Target target : targets) {

            log.debug(
                    "국가별 이슈 분석 작업 등록: "
                            + "issueId={}, issueName={}, "
                            + "countryCode={}, countryName={}, articleCount={}",
                    target.issueId(),
                    target.issueName(),
                    target.countryCode(),
                    target.countryName(),
                    target.articleCount()
            );

            try {
                workerService.analyze(
                        target,
                        periodStart,
                        createdAt
                );
                submittedCount++;
            } catch (TaskRejectedException exception) {
                log.error("국가별 이슈 분석 작업 등록 실패: issueId={}, countryCode={}, createdAt={}",
                        target.issueId(), target.countryCode(), createdAt, exception);
            }
        }

        /*
         * 여기서 "완료"는 GMS 분석 완료를 의미하지 않는다.
         *
         * 모든 Target을 비동기 Worker Queue에 전달했다는 의미다.
         */
        log.info(
                "국가별 이슈 분석 작업 등록 완료: "
                        + "targetCount={}, submittedCount={}, periodStart={}, createdAt={}",
                targets.size(),
                submittedCount,
                periodStart,
                createdAt
        );
    }
}
