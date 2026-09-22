package com.ssafy.witw.infra.kafka.dbwriter;

import com.fasterxml.jackson.annotation.JsonProperty;
import tools.jackson.databind.JsonNode;

import java.time.OffsetDateTime;

public record DbWriterEvent(
        @JsonProperty("event_type") String eventType,
        @JsonProperty("occurred_at") OffsetDateTime occurredAt,
        JsonNode payload
) {
}
