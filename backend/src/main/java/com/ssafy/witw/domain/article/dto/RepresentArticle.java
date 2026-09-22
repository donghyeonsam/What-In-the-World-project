package com.ssafy.witw.domain.article.dto;

import com.ssafy.witw.domain.article.dao.ArticleRepository.RepresentArticleProjection;

import java.time.LocalDateTime;

public record RepresentArticle(
        String articleId,
        String articleTitle,
        ArticleTone articleTone,
        String articlePublisher,
        String url,
        String summary,
        LocalDateTime publishedAt
) {
    public RepresentArticle(String articleId, String articleTitle, ArticleTone articleTone,
                            String articlePublisher, String url, LocalDateTime publishedAt) {
        this(articleId, articleTitle, articleTone, articlePublisher, url, null, publishedAt);
    }

    public static RepresentArticle from(RepresentArticleProjection row) {
        return new RepresentArticle(
                row.getArticleId(),
                row.getArticleTitle(),
                ArticleTone.fromScore(row.getArticleToneScore()),
                row.getArticlePublisher(),
                row.getUrl(),
                row.getSummary(),
                row.getPublishedAt()
        );
    }
}
