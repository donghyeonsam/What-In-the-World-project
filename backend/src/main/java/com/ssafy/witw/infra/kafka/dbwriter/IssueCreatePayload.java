package com.ssafy.witw.infra.kafka.dbwriter;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

public record IssueCreatePayload(
        @JsonProperty("theme_id") Long themeId,
        String name,
        List<BigDecimal> embedding,
        @JsonProperty("article_ids") List<String> articleIds,
        @JsonProperty("article_similarities") Map<String, BigDecimal> articleSimilarities,
        @JsonProperty("first_seen_at") OffsetDateTime firstSeenAt
) {
}
