package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 국가별 이슈 분석을 GMS LLM에 요청하는 Service.
 *
 * PromptService가 생성한 system/user message를
 * GMS의 OpenAI-compatible /chat/completions API로 전달한다.
 *
 * 이 Service는 GMS 호출과 응답 content 추출까지만 담당한다.
 * LLM이 반환한 분석 JSON의 구조 및 값 검증은
 * IssueCountryAnalysisResponseValidator가 담당한다.
 */
@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisGmsService {

    private final ObjectMapper objectMapper;

    /*
     * Java 기본 HttpClient를 사용한다.
     *
     * 별도의 HTTP 라이브러리 의존성을 추가하지 않고
     * GMS API를 호출할 수 있다.
     */
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    /**
     * GMS OpenAI-compatible API의 Base URL.
     */
    @Value("${analysis.gms.base-url:https://gms.ssafy.io/gmsapi/api.openai.com/v1}")
    private String baseUrl;

    /**
     * GMS 인증에 사용하는 API Key.
     *
     * 실제 값은 application.yml 또는 환경변수에서 주입한다.
     */
    @Value("${analysis.gms.api-key:}")
    private String apiKey;

    /**
     * 국가별 뉴스 분석에 사용할 GMS 모델.
     */
    @Value("${analysis.gms.model:gpt-4o-mini}")
    private String model;

    /**
     * 한 번의 GMS 요청을 기다리는 최대 시간.
     */
    @Value("${analysis.gms.timeout-seconds:30}")
    private long timeoutSeconds;

    /**
     * 네트워크 오류, timeout, 429, 5xx 발생 시 최대 시도 횟수.
     */
    @Value("${analysis.gms.max-attempts:3}")
    private int maxAttempts;

    /**
     * GMS가 생성할 수 있는 최대 토큰 수.
     */
    @Value("${analysis.gms.max-tokens:1200}")
    private int maxTokens;

    /**
     * PromptService에서 준비한 프롬프트를 GMS로 전달하고
     * choices[0].message.content 값을 반환한다.
     */
    public String analyze(PreparedPrompt prompt) {
        if (prompt == null) {
            throw new IllegalArgumentException("PreparedPrompt is required");
        }

        validateConfig();

        String requestBody = buildRequestBody(prompt);
        Exception lastException = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {

            try {
                HttpResponse<String> response = sendRequest(requestBody);
                int statusCode = response.statusCode();

                if (statusCode >= 200 && statusCode < 300) {
                    return extractContent(response.body());
                }

                /*
                 * 429: 요청 제한
                 * 5xx: GMS 또는 upstream 서버의 일시적 오류
                 *
                 * 이런 경우에는 재시도를 허용한다.
                 */
                if (statusCode == 429 || statusCode >= 500) {
                    lastException = new GmsAnalysisException(
                            "GMS request failed with retryable status: "
                                    + statusCode
                    );

                    if (attempt < maxAttempts) {
                        waitBeforeRetry(attempt);
                        continue;
                    }
                }

                /*
                 * 4xx 중 429가 아닌 경우는
                 * 잘못된 요청이나 인증 문제일 가능성이 높으므로
                 * 반복해도 해결되지 않는다고 판단하고 즉시 실패한다.
                 */
                throw new GmsAnalysisException(
                        "GMS request failed. status="
                                + statusCode
                                + ", body="
                                + shortenResponse(response.body())
                );

            } catch (HttpTimeoutException exception) {
                lastException = exception;

                if (attempt < maxAttempts) {
                    waitBeforeRetry(attempt);
                    continue;
                }

            } catch (IOException exception) {
                lastException = exception;

                if (attempt < maxAttempts) {
                    waitBeforeRetry(attempt);
                    continue;
                }

            } catch (InterruptedException exception) {
                /*
                 * Worker Thread가 종료 요청을 받은 경우
                 * interrupt 상태를 복원하고 즉시 작업을 종료한다.
                 */
                Thread.currentThread().interrupt();

                throw new GmsAnalysisException(
                        "GMS request was interrupted",
                        exception
                );
            }
        }

        throw new GmsAnalysisException(
                "GMS analysis failed after "
                        + maxAttempts
                        + " attempts",
                lastException
        );
    }

    /**
     * OpenAI-compatible chat/completions 요청 JSON을 생성한다.
     */
    private String buildRequestBody(PreparedPrompt prompt) {

        Map<String, Object> request = new LinkedHashMap<>();

        request.put("model", model);

        // 분석 결과의 일관성을 높이기 위해 낮은 temperature 사용
        request.put("temperature", 0.1);

        request.put("max_tokens", maxTokens);

        /*
         * LLM에게 일반 텍스트가 아니라
         * JSON 객체 형태로 응답하도록 요청한다.
         */
        request.put(
                "response_format",
                Map.of("type", "json_object")
        );

        request.put(
                "messages",
                List.of(
                        Map.of(
                                "role", "system",
                                "content", prompt.systemMessage()
                        ),
                        Map.of(
                                "role", "user",
                                "content", prompt.userMessage()
                        )
                )
        );

        return objectMapper.writeValueAsString(request);
    }

    /**
     * 실제 HTTP 요청을 수행한다.
     */
    private HttpResponse<String> sendRequest(String requestBody)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(completionUrl()))
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .header(
                        "Authorization",
                        "Bearer " + apiKey
                )
                .header(
                        "Content-Type",
                        "application/json"
                )
                .POST(
                        HttpRequest.BodyPublishers.ofString(
                                requestBody,
                                StandardCharsets.UTF_8
                        )
                )
                .build();

        return httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8
                )
        );
    }

    /**
     * GMS 응답에서
     *
     * choices[0].message.content
     *
     * 값을 추출한다.
     */
    private String extractContent(String responseBody) {

        Object parsed;

        try {
            parsed = objectMapper.readValue(
                    responseBody,
                    Object.class
            );
        } catch (JacksonException exception) {
            throw new GmsAnalysisException(
                    "GMS response is not valid JSON",
                    exception
            );
        }

        if (!(parsed instanceof Map<?, ?> root)) {
            throw new GmsAnalysisException(
                    "GMS response must be a JSON object"
            );
        }

        Object choicesValue = root.get("choices");

        if (!(choicesValue instanceof List<?> choices)
                || choices.isEmpty()) {
            throw new GmsAnalysisException(
                    "GMS response does not contain choices"
            );
        }

        Object firstChoice = choices.get(0);

        if (!(firstChoice instanceof Map<?, ?> choice)) {
            throw new GmsAnalysisException(
                    "GMS response choice is invalid"
            );
        }

        Object messageValue = choice.get("message");

        if (!(messageValue instanceof Map<?, ?> message)) {
            throw new GmsAnalysisException(
                    "GMS response message is invalid"
            );
        }

        Object contentValue = message.get("content");

        if (!(contentValue instanceof String content)
                || content.isBlank()) {
            throw new GmsAnalysisException(
                    "GMS response content is empty"
            );
        }

        /*
         * 여기서는 content의 JSON 구조는 검사하지 않는다.
         *
         * 다음 단계의 ResponseValidator에서
         * title / summary / details / evidenceArticleIds 등을 검증한다.
         */
        return content.strip();
    }

    /**
     * Base URL 뒤에 /chat/completions를 붙인다.
     *
     * 설정값 자체가 이미 /chat/completions로 끝나는 경우에는
     * 중복으로 붙이지 않는다.
     */
    private String completionUrl() {

        String normalized = baseUrl.strip();

        while (normalized.endsWith("/")) {
            normalized = normalized.substring(
                    0,
                    normalized.length() - 1
            );
        }

        if (normalized.endsWith("/chat/completions")) {
            return normalized;
        }

        return normalized + "/chat/completions";
    }

    /**
     * GMS 호출에 필요한 설정값을 실행 전에 검증한다.
     */
    private void validateConfig() {

        if (baseUrl == null || baseUrl.isBlank()) {
            throw new GmsAnalysisException(
                    "analysis.gms.base-url is required"
            );
        }

        if (apiKey == null || apiKey.isBlank()) {
            throw new GmsAnalysisException(
                    "analysis.gms.api-key is required"
            );
        }

        if (model == null || model.isBlank()) {
            throw new GmsAnalysisException(
                    "analysis.gms.model is required"
            );
        }

        if (timeoutSeconds <= 0) {
            throw new GmsAnalysisException(
                    "analysis.gms.timeout-seconds must be positive"
            );
        }

        if (maxAttempts < 1) {
            throw new GmsAnalysisException(
                    "analysis.gms.max-attempts must be positive"
            );
        }

        if (maxTokens < 1) {
            throw new GmsAnalysisException(
                    "analysis.gms.max-tokens must be positive"
            );
        }
    }

    /**
     * 재시도 간 간단한 exponential backoff를 적용한다.
     *
     * 1차 실패 -> 1초
     * 2차 실패 -> 2초
     * 이후 최대 4초
     */
    private static void waitBeforeRetry(int attempt) {

        long waitSeconds = Math.min(
                1L << (attempt - 1),
                4L
        );

        try {
            Thread.sleep(waitSeconds * 1000);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();

            throw new GmsAnalysisException(
                    "GMS retry wait was interrupted",
                    exception
            );
        }
    }

    /**
     * 오류 로그에 GMS 응답 전체가 지나치게 길게 찍히는 것을 방지한다.
     */
    private static String shortenResponse(String body) {

        if (body == null) {
            return "";
        }

        String normalized = body.strip();

        return normalized.length() <= 500
                ? normalized
                : normalized.substring(0, 500);
    }

    /**
     * GMS 통신 또는 응답 구조에 문제가 있을 때 사용하는 예외.
     */
    public static class GmsAnalysisException
            extends RuntimeException {

        public GmsAnalysisException(String message) {
            super(message);
        }

        public GmsAnalysisException(
                String message,
                Throwable cause
        ) {
            super(message, cause);
        }
    }
}