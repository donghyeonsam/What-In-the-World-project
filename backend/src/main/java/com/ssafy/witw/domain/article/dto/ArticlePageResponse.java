package com.ssafy.witw.domain.article.dto;

import java.util.List;

public record ArticlePageResponse(
        List<ArticleListItem> items,
        int page,
        int size,
        long totalElements,
        long totalPages) {
}
