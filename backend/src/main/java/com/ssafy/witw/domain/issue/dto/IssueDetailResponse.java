package com.ssafy.witw.domain.issue.dto;

import com.ssafy.witw.domain.article.dto.RepresentArticle;

import java.util.List;

public record IssueDetailResponse(
        CountryIssueDetail issueDetail,
        List<RepresentArticle> articleInfoList
) { }
