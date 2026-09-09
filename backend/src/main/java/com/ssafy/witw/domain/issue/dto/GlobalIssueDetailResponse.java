package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.country.dto.CountryTone;

import java.util.List;

public record GlobalIssueDetailResponse(
        IssueInfo issueInfo,
        List<CountryTone> countryTones
) { }
