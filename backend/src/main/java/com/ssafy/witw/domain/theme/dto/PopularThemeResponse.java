package com.ssafy.witw.domain.theme.dto;

import java.util.List;

public record PopularThemeResponse(
        String countryCode,
        String countryName,
        List<PopularTheme> popularThemes
) { }
