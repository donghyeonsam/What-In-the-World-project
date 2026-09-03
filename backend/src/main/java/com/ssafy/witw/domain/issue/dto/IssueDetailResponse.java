package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.article.dto.ArticleInfo;

import java.util.List;

public record IssueDetailResponse(
        String themeName,
        CountryIssueDetail issueDetail,
        List<ArticleInfo> articleInfoList
) { }