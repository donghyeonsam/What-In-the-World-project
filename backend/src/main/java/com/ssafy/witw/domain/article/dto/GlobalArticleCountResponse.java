package com.ssafy.witw.domain.article.dto;


import java.time.LocalDateTime;

public record GlobalArticleCountResponse(
        long totalArticleCount,
        long todayArticleCount,
        LocalDateTime updatedAt
) { }
