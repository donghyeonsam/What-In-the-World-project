package com.ssafy.witw.domain.theme.dto;

import java.time.LocalDateTime;
import java.util.List;

public record PopularTheme(
        long themeId,
        String fieldName,
        String themeName,
        long articleCount24,

        ThemeTimeStamp themeTimeStamp
) { }

record ThemeTimeStamp(
        int interval,
        List<TimeStamp> timestamp
){}

record TimeStamp(
        LocalDateTime time,
        long articleCount
){}