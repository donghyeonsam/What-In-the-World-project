package com.ssafy.witw.domain.country.dto;

public record CountryTone(
        CountryPoint country,
        double toneAvg,
        double toneMax,
        double toneMin,
        double toneSd,
        long articleCount
) { }
