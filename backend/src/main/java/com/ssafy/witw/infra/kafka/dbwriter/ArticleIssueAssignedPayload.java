package com.ssafy.witw.infra.kafka.dbwriter;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

public record ArticleIssueAssignedPayload(
        @JsonProperty("article_id") String articleId,
        @JsonProperty("issue_id") Long issueId,
        BigDecimal similarity
) {
}
