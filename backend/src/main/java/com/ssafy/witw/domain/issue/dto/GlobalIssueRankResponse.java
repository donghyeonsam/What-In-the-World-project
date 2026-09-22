package com.ssafy.witw.domain.issue.dto;

import java.time.LocalDateTime;
import java.util.List;

public record GlobalIssueRankResponse(
        long totalArticleCount,
        long recent24ArticleCount,
        List<GlobalIssue> globalIssues
) {
    public record GlobalIssue(
            long issueId,
            String fieldName,
            String themeName,
            String issueName,
            LocalDateTime firstSeenAt,
            String scoreVersion,
            Double globalHeatScore,
            Long countryCount
    ) { }
}
