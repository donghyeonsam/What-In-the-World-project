package com.ssafy.witw.analysis.scheduler;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisTargetService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

/**
 * 국가별 이슈 분석의 실행 시각을 정한다.
 * analysis.scheduler.cron으로 실행 주기를 변경하고,
 * analysis.scheduler.enabled=false로 실행을 비활성화할 수 있다.
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

    private static final ZoneId ANALYSIS_ZONE = ZoneId.of("Asia/Seoul");

    private final IssueCountryAnalysisTargetService targetService;

    // 0 0 */3 * * * 으로 하면 3시간에 한 번씩 수행
    @Scheduled(cron = "${analysis.scheduler.cron:0 0 * * * *}", zone = "Asia/Seoul")
    public void runAnalysis() {
        // 실제 실행 시각을 한 번만 정한다. 결과의 created_at에도 같은 값을 사용한다.
        LocalDateTime createdAt = LocalDateTime.now(ANALYSIS_ZONE);
        LocalDateTime periodStart = createdAt.minusHours(24);

        List<Target> targets = targetService.findTargets(periodStart, createdAt);

        log.info("국가별 이슈 분석 대상 선정: periodStart={}, createdAt={}, targetCount={}",
                periodStart, createdAt, targets.size());
        targets.forEach(target -> log.debug(
                "분석 대상: issueId={}, countryCode={}, articleCount={}",
                target.issueId(), target.countryCode(), target.articleCount()
        ));

        // TODO: 각 분석 대상의 기사 조회·LLM 분석·결과 저장을 연결한다.
        // 결과의 created_at에는 위에서 정한 createdAt을 그대로 전달한다.
    }
}
