package com.ssafy.witw.domain.theme.dto;

import java.time.LocalDate;
import java.util.List;

public record PopularThemeResponse(
        String countryCode,
        String countryName,
        ThemeTimeStamp themeTimeStamp
) {
}

record ThemeTimeStamp(
        String interval,
        List<TimeStamp> timestamp
){}

record TimeStamp(
        LocalDate time,
        long articleCount
){}