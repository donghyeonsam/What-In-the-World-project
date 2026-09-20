package com.ssafy.witw.domain.notification.event;

import java.util.Set;

public record NotificationsCreatedEvent(
        Set<Long> userIds
) {
    public NotificationsCreatedEvent {
        userIds = Set.copyOf(userIds);
    }
}