package com.ssafy.witw.domain.auth.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "ssafy.oauth")
public record SsafyOAuthProperties (
        String clientId,
        String clientSecret,
        String redirectUri,
        String tokenUri,
        String userInfoUri
){
}
