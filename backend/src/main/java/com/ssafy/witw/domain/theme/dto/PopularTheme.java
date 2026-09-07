package com.ssafy.witw.domain.theme.dto;

// 시간대별 추이 없이 테마와 기사 수만 담는 요약 (국가 메인 등)
public record PopularTheme(
        long themeId,
        String fieldName,
        String themeName,
        long articleCount24
) { }
