package com.ssafy.witw.domain.notification.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class NotificationBatchService {

    private static final String JOB_NAME = "THEME_NOTIFICATION";
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    private final JdbcTemplate jdbcTemplate;
    private final NotificationGenerationService notificationGenerationService;

    @Transactional
    public boolean processNextPeriod() {
        // 다른 서버가 처리 중이면 기다리지 않고 건너뛴다.
        List<LocalDateTime> starts = jdbcTemplate.query(
                """
                SELECT next_period_start
                FROM notification_job_state
                WHERE job_name = ?
                FOR UPDATE SKIP LOCKED
                """,
                (rs, rowNum) ->
                        rs.getTimestamp("next_period_start").toLocalDateTime(),
                JOB_NAME
        );

        if (starts.isEmpty()) return false;


        LocalDateTime periodStart = starts.getFirst();
        LocalDateTime periodEnd = periodStart.plusMinutes(10);

        // 기사 저장 트랜잭션이 끝날 시간을 고려해 2분 여유를 둔다.
        LocalDateTime readyUntil = LocalDateTime.now(KST).minusMinutes(2);

        if (periodEnd.isAfter(readyUntil)) return false;


        int createdCount = notificationGenerationService.generate(periodStart, periodEnd);

        jdbcTemplate.update(
                """
                UPDATE notification_job_state
                SET next_period_start = ?
                WHERE job_name = ?
                """,
                Timestamp.valueOf(periodEnd),
                JOB_NAME
        );

        log.info(
                "알림 집계 처리: start={}, end={}, createdCount={}",
                periodStart,
                periodEnd,
                createdCount
        );

        return true;
    }
}