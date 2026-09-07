package com.ssafy.witw.domain.country.dto;

// 지구본 위에 국가를 찍기 위한 공통 정보
public record CountryPoint(
        String countryCode,
        String countryName,
        double lng,
        double lat
) { }
