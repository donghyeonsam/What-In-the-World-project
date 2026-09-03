package com.ssafy.witw.domain.article.dto;

import java.time.LocalDateTime;

public record RepresentArticle(
        String articleId,
        String articleTitle,
        ArticleTone articleTone,
        String articlePublisher,
        LocalDateTime publishedAt
) {
}
