package com.ssafy.witw.domain.notification.dto.response;

import java.util.List;

public record NotificationListResponse(
        List<NotificationResponse> notifications,
        int page,
        int size,
        boolean hasNext
) {
}