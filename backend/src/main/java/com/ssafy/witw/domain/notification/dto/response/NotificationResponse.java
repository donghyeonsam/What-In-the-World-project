package com.ssafy.witw.domain.notification.dto.response;

import com.ssafy.witw.domain.notification.entity.Notification;
import com.ssafy.witw.domain.theme.entity.Theme;

import java.time.LocalDateTime;

public record NotificationResponse(
        Long id,
        String title,
        String message,
        Long fieldId,
        String fieldName,
        Long themeId,
        String themeName,
        Integer articleCount,
        LocalDateTime createdAt,
        LocalDateTime readAt
) {

    public static NotificationResponse from(Notification notification) {
        Theme theme = notification.getTheme();

        return new NotificationResponse(
                notification.getId(),
                notification.getTitle(),
                notification.getMessage(),
                theme.getField().getId(),
                theme.getField().getName(),
                theme.getId(),
                theme.getName(),
                notification.getArticleCount(),
                notification.getCreatedAt(),
                notification.getReadAt()
        );
    }
}