package com.ssafy.witw.domain.theme.dto;

import java.time.LocalDateTime;
import java.util.List;

// 인기 테마 + 시간대별 기사 수 추이
public record PopularThemeTrend(
        long themeId,
        String fieldName,
        String themeName,
        long articleCount24,
        ThemeTimeStamp themeTimeStamp
) {
    public record ThemeTimeStamp(
            int interval,
            List<TimeStamp> timestamp
    ) { }

    public record TimeStamp(
            LocalDateTime time,
            long articleCount
    ) { }
}
