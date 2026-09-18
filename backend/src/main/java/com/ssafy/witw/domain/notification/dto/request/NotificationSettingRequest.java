package com.ssafy.witw.domain.notification.dto.request;

import jakarta.validation.constraints.NotNull;

public record NotificationSettingRequest(
        @NotNull(message = "알림 활성화 여부는 필수입니다.")
        Boolean enabled
) {
}