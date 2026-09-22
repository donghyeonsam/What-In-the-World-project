package com.ssafy.witw.domain.auth.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.auth.config.SsafyOAuthProperties;
import com.ssafy.witw.domain.auth.dto.response.SsafyTokenResponse;
import com.ssafy.witw.domain.auth.dto.response.SsafyUserInfo;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;


@Component
public class SsafyOAuthClient {

    private final RestClient restClient;
    private final SsafyOAuthProperties properties;

    public SsafyOAuthClient(
            RestClient.Builder restClientBuilder,
            SsafyOAuthProperties properties
    ) {
        this.restClient = restClientBuilder.build();
        this.properties = properties;
    }

    public SsafyUserInfo authenticate(String code){
        if(isBlank(properties.clientId()) || isBlank(properties.clientSecret())
            || isBlank(properties.redirectUri()))
            throw new GlobalException(ErrorCode.SSAFY_SERVER_ERROR);

        try {
            SsafyTokenResponse token = requestToken(code);

            if(token == null || token.accessToken() == null
                || token.accessToken().isBlank())
                throw new GlobalException(ErrorCode.SSAFY_AUTH_FAILED);

            SsafyUserInfo userInfo = requestUserInfo(token.accessToken());

            if(userInfo == null || userInfo.userId() == null
                || userInfo.userId().isBlank()
                || userInfo.email() == null
                || userInfo.email().isBlank())
                throw new GlobalException(ErrorCode.SSAFY_AUTH_FAILED);
            return userInfo;
        } catch (HttpClientErrorException exception) {
            throw new GlobalException(ErrorCode.SSAFY_AUTH_FAILED, exception);
        } catch (RestClientException exception){
            throw new GlobalException(ErrorCode.SSAFY_SERVER_ERROR, exception);
        }
    }

    private SsafyTokenResponse requestToken(String code) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("client_id", properties.clientId());
        form.add("client_secret", properties.clientSecret());
        form.add("code", code);
        form.add("grant_type", "authorization_code");
        form.add("redirect_uri", properties.redirectUri());

        return restClient.post()
                .uri(properties.tokenUri())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .retrieve()
                .body(SsafyTokenResponse.class);
    }

    private SsafyUserInfo requestUserInfo(String accessToken) {
        return restClient.get()
                .uri(properties.userInfoUri())
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(SsafyUserInfo.class);
    }


    private boolean isBlank(String value){
        return value == null || value.isBlank();
    }

}
