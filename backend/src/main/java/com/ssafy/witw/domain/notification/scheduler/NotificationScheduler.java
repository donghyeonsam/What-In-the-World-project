package com.ssafy.witw.domain.notification.scheduler;

import com.ssafy.witw.domain.notification.service.NotificationBatchService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "notification.scheduler",
        name = "enabled",
        havingValue = "true"
)
public class NotificationScheduler {

    private static final int MAX_PERIODS_PER_RUN = 6;

    private final NotificationBatchService notificationBatchService;

    @Scheduled(
            fixedDelayString = "${notification.scheduler.delay-ms:60000}",
            initialDelayString = "${notification.scheduler.initial-delay-ms:10000}"
    )
    public void run() {
        try {
            for (int i = 0; i < MAX_PERIODS_PER_RUN; i++) {
                if (!notificationBatchService.processNextPeriod()) {
                    break;
                }
            }
        } catch (Exception exception) {
            log.error("알림 집계 실패. 다음 실행에서 재시도합니다.", exception);
        }
    }
}