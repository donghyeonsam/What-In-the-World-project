package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.country.dto.CountryTone;

import java.util.List;

public record GlobalIssueResponse(
        String fieldName,
        String themeName,
        String issueName,
        long articleCount24,
		long toneScore,
        int relatedCountry,
        List<CountryTone> countryTone
) { }
