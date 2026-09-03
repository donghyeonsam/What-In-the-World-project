package com.ssafy.witw.domain.country.dto;

public record CountryCount(
        String countryCode,
        String countryName,
        double lng, // 지구본 위 좌표 표시
        double lat,
        long articleCount
){}