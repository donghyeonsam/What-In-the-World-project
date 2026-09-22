package com.ssafy.witw.domain.auth.dto.response;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record SsafyTokenResponse (
        @JsonProperty("token_type")
        String tokenType,

        @JsonProperty("access_token")
        String accessToken
){
}
