package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.dto.CountryTone;

import java.util.List;

public record IssueOverviewResponse(
        IssuePreview issuePreview,
        List<CountryTone> countryTones,
        List<RepresentArticle> representArticles
) {
    public record IssuePreview(
            String issueTitle,
            String themeTitle,
            long articleCount
    ) { }
}
