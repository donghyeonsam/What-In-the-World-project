package com.ssafy.witw.domain.theme.dto;

public record PopularTheme(
        long themeId,
        String fieldName,
        String themeName,
        long articleCount24
) { }
