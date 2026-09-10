package com.ssafy.witw.infra.kafka.dbwriter;

import com.fasterxml.jackson.annotation.JsonProperty;

public record MentionedCountryPayload(
        @JsonProperty("country_code") String countryCode,
        Integer count
) {
}
