package com.ssafy.witw.domain.issue.dto;

public record ToneDetail(
        double toneAvg,
        double toneSd,
        long articleCount
){}
