package com.ssafy.witw.domain.issue.dto;

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
            LocalDateTime firstSeenAt
    ) { }
}
