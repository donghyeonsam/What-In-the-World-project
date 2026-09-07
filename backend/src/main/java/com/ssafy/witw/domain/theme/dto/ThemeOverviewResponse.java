package com.ssafy.witw.domain.theme.dto;

import com.ssafy.witw.domain.article.dto.RepresentArticle;

import java.util.List;

public record ThemeOverviewResponse(
        Long themeId,
        String themeName,
        String themeDescription,
        List<PrimaryIssue> primaryIssues,
        List<RepresentArticle> representArticles
) {
    public record PrimaryIssue(Long issueId, String issueTitle) {
    }
}
