package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.country.dto.CountryTone;

import java.time.LocalDateTime;
import java.util.List;

public record GlobalIssueRankResponse(
        List<GlobalIssue> globalIssues
) {
    public record GlobalIssue(
            long issueId,
            String fieldName,
            String themeName,
            String issueName,
            long articleCount,
            List<CountryTone> countryTones,
            LocalDateTime firstSeenAt
    ) { }
}
