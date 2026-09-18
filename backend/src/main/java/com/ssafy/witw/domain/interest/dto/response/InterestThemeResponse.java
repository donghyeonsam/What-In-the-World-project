package com.ssafy.witw.domain.interest.dto.response;

import com.ssafy.witw.domain.interest.dao.UserInterestThemeRepository.InterestThemeRow;

public record InterestThemeResponse (
        Long themeId,
        String themeName
){
    public static InterestThemeResponse from(InterestThemeRow row){
        return new InterestThemeResponse(
                row.getThemeId(),
                row.getThemeName()
        );
    }
}
