package com.ssafy.witw.domain.article.dto;

import java.util.List;

public record ArticleFiltersResponse(
        List<CountryOption> countries,
        List<FieldOption> fields) {

    public record CountryOption(String countryCode, String countryName) {
    }

    public record FieldOption(Long fieldId, String fieldName, List<ThemeOption> themes) {
    }

    public record ThemeOption(Long themeId, String themeName) {
    }
}
