package com.ssafy.witw.domain.notification.service;

import com.ssafy.witw.domain.notification.dao.NotificationRepository;
import com.ssafy.witw.domain.notification.event.NotificationsCreatedEvent;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.HashSet;

@Service
@RequiredArgsConstructor
public class NotificationGenerationService {

    private final NotificationRepository notificationRepository;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public int generate(LocalDateTime periodStart, LocalDateTime periodEnd) {
        if (periodStart == null
                || periodEnd == null
                || !periodStart.isBefore(periodEnd)) {
            throw new IllegalArgumentException("알림 집계 시작 시각은 종료 시각보다 이전이어야 합니다.");
        }
        int createdCount = notificationRepository.createThemeNotifications(periodStart, periodEnd);

        if (createdCount > 0) {
            var userIds = notificationRepository.findRecipientIdsByPeriod(periodStart, periodEnd);
            eventPublisher.publishEvent(new NotificationsCreatedEvent(new HashSet<>(userIds)));
        }

        return createdCount;
    }
}