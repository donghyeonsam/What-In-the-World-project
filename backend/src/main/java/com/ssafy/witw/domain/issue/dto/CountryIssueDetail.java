package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.country.dto.CountryCount;
import com.ssafy.witw.domain.country.dto.CountryTone;

import java.util.List;

public record CountryIssueDetail(
        long issueId,
        String fieldName,
        String themeName,
        String countryCode,
        String countryName,
        ToneDetail toneDetail,
        List<CountryCount> countryCountList,
        List<CountryTone> countryToneList
) {}