package com.ssafy.witw.infra;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

@ConfigurationProperties(prefix = "app.cors")
public record CorsProperties(List<String> allowedOrigins, List<String> allowedMethods, List<String> allowedHeaders) {
}
