package com.ssafy.witw.domain.auth.dto.response;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record SsafyUserInfo (
        String userId,
        String email
){
}
