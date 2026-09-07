package com.ssafy.witw.domain.article.dto;

import java.time.LocalDateTime;

public record ArticleInfo(
        String articleId,
        String title,
        String publisher,
        double toneScore,
        LocalDateTime publishedAt
) { }
