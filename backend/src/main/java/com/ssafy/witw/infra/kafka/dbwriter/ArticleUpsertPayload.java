package com.ssafy.witw.infra.kafka.dbwriter;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;

public record ArticleUpsertPayload(
        @JsonProperty("article_id") String articleId,
        @JsonProperty("publisher_country_code") String publisherCountryCode,
        @JsonProperty("theme_id") Long themeId,
        @JsonProperty("theme_relevance_score") BigDecimal themeRelevanceScore,
        String publisher,
        String url,
        // 기사 타이틀 번역 내용
        @JsonProperty("translated_title") String translatedTitle,
        // 기사 본문 3문장 한국어 요약
        String summary,
        // 그 요약문의 E5 임베딩(768차원). 요약이 실패한 기사는 null 이다.
        @JsonProperty("summary_embedding") List<BigDecimal> summaryEmbedding,
        @JsonProperty("original_title") String originalTitle,
        @JsonProperty("crawled_at") OffsetDateTime crawledAt,
        List<BigDecimal> embedding,
        @JsonProperty("tone_score") BigDecimal toneScore,
        @JsonProperty("published_at") OffsetDateTime publishedAt,
        @JsonProperty("mentioned_countries") List<MentionedCountryPayload> mentionedCountries
) {
}