package com.ssafy.witw.domain.theme.dto;

import java.util.List;

public record FieldThemesResponse(
        Long fieldId,
        String fieldName,
        List<ThemeCount> themes
) {
    public record ThemeCount(Long themeId, String themeName, long articleCount24) { }
}
