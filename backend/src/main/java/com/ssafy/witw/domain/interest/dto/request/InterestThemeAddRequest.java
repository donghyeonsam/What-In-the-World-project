package com.ssafy.witw.domain.interest.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record InterestThemeAddRequest (
        @NotNull(message = "themeId는 필수입니다.")
        @Positive(message = "themeId는 1 이상이어야 합니다.")
        Long themeId
){
}
