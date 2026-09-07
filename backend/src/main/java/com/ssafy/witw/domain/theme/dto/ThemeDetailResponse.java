package com.ssafy.witw.domain.theme.dto;

import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.issue.dto.IssueInfo;

import java.util.List;

public record ThemeDetailResponse (
    long id,
    List<IssueInfo> issues,
    List<RepresentArticle> articles
){}

