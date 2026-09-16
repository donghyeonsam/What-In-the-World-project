package com.ssafy.witw.domain.article.dto;

import com.ssafy.witw.domain.article.entity.Article;

import java.time.OffsetDateTime;

public record ArticleDetailResponse(
        String articleId,
        String articleTitle,
        String summary,
        String url,
        String articlePublisher,
        OffsetDateTime publishedAt,
        String countryCode,
        String countryName,
        Long fieldId,
        String fieldName,
        Long themeId,
        String themeName) {

    public static ArticleDetailResponse from(Article article) {
        ArticleListItem item = ArticleListItem.from(article);
        return new ArticleDetailResponse(
                item.articleId(),
                item.articleTitle(),
                item.summary(),
                article.getUrl(),
                item.articlePublisher(),
                item.publishedAt(),
                item.countryCode(),
                item.countryName(),
                item.fieldId(),
                item.fieldName(),
                item.themeId(),
                item.themeName());
    }
}
