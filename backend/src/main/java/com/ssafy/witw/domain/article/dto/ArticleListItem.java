package com.ssafy.witw.domain.article.dto;

import com.ssafy.witw.domain.article.entity.Article;

import java.time.OffsetDateTime;
import java.time.ZoneId;

public record ArticleListItem(
        String articleId,
        String articleTitle,
        String summary,
        String articlePublisher,
        OffsetDateTime publishedAt,
        String countryCode,
        String countryName,
        Long fieldId,
        String fieldName,
        Long themeId,
        String themeName) {

    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    public static ArticleListItem from(Article article) {
        String translated = article.getTranslatedTitle();
        String title = translated != null && !translated.isBlank()
                ? translated : article.getOriginalTitle();
        return new ArticleListItem(
                article.getId(),
                title,
                article.getSummary(),
                article.getPublisher(),
                article.getPublishedAt().atZone(KST).toOffsetDateTime(),
                article.getPublisherCountryCode().getCountryCode(),
                article.getPublisherCountryCode().getNameKo(),
                article.getTheme().getField().getId(),
                article.getTheme().getField().getName(),
                article.getTheme().getId(),
                article.getTheme().getName());
    }
}
