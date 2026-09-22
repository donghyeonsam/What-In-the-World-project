package com.ssafy.witw.domain.auth.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SsafyOAuthProperties.class)
public class SsafyOAuthConfig {
    @Bean
    public RestClient.Builder restClientBuilder(){
        return RestClient.builder();
    }
}
