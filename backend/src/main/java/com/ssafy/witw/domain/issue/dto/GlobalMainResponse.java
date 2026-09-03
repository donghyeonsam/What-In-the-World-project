package com.ssafy.witw.domain.issue.dto;

import java.util.List;

public record GlobalMainResponse(
        long totalArticleCount,
        long todayArticleCount,
        List<IssueRanking> issueRankingList
) {}

record IssueRanking(
        long issueId,
        String fieldName,
        String themeName,
        String issueName
) {}