package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.service.IssueCountryAnalysisGmsService.GmsAnalysisException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.json.JsonMapper;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class IssueCountryAnalysisGmsServiceTest {
    private final JsonMapper mapper = JsonMapper.builder().build();
    private final HttpClient client = mock(HttpClient.class);
    private final IssueCountryAnalysisGmsService service = new IssueCountryAnalysisGmsService(mapper);
    private final PreparedPrompt prompt = new PreparedPrompt("system", "{\"representativeArticles\":[]}",
            List.of("private-article-id"), 10, 5);
    private static final String CONTENT = "{\"title\":\"t\",\"summary\":\"s\",\"details\":[\"d\"]}";

    @BeforeEach
    void isolate_http_and_use_only_test_credentials() {
        ((HttpClient) ReflectionTestUtils.getField(service, "httpClient")).close();
        ReflectionTestUtils.setField(service, "httpClient", client);
        ReflectionTestUtils.setField(service, "baseUrl", "http://127.0.0.1:1/v1");
        ReflectionTestUtils.setField(service, "apiKey", "test-key");
        ReflectionTestUtils.setField(service, "model", "test-model");
        ReflectionTestUtils.setField(service, "timeoutSeconds", 1L);
        ReflectionTestUtils.setField(service, "maxAttempts", 2);
        ReflectionTestUtils.setField(service, "maxTokens", 1200);
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://127.0.0.1:1/v1/", "http://127.0.0.1:1/v1/chat/completions/"})
    void sends_only_messages_and_extracts_content(String baseUrl) throws Exception {
        ReflectionTestUtils.setField(service, "baseUrl", baseUrl);
        HttpResponse<String> success = response(200, envelope());
        when(client.send(any(), any(HttpResponse.BodyHandler.class))).thenReturn(success);
        assertThat(service.analyze(prompt)).isEqualTo(CONTENT);
        ArgumentCaptor<HttpRequest> request = ArgumentCaptor.forClass(HttpRequest.class);
        verify(client).send(request.capture(), any(HttpResponse.BodyHandler.class));
        assertThat(request.getValue().uri().toString()).isEqualTo("http://127.0.0.1:1/v1/chat/completions");
        assertThat(request.getValue().headers().firstValue("Authorization")).contains("Bearer test-key");
        String body = requestBody(request.getValue());
        assertThat(body).doesNotContain("private-article-id", "representativeArticleIds", "evidenceArticleIds");
        Map<?, ?> json = mapper.readValue(body, Map.class);
        assertThat(json.get("model")).isEqualTo("test-model");
        assertThat(json.get("response_format")).isEqualTo(Map.of("type", "json_object"));
        assertThat(json.get("messages")).isEqualTo(List.of(
                Map.of("role", "system", "content", prompt.systemMessage()),
                Map.of("role", "user", "content", prompt.userMessage())));
    }

    @Test
    void missing_api_key_fails_before_any_http_request() {
        ReflectionTestUtils.setField(service, "apiKey", "");
        assertThatThrownBy(() -> service.analyze(prompt)).isInstanceOf(GmsAnalysisException.class)
                .hasMessageContaining("api-key");
        verifyNoInteractions(client);
    }

    @ParameterizedTest
    @ValueSource(ints = {429, 503})
    void retries_transient_status_and_then_succeeds(int status) throws Exception {
        HttpResponse<String> failure = response(status, "temporary");
        HttpResponse<String> success = response(200, envelope());
        when(client.send(any(), any(HttpResponse.BodyHandler.class)))
                .thenReturn(failure, success);
        assertThat(service.analyze(prompt)).isEqualTo(CONTENT);
        verify(client, times(2)).send(any(), any(HttpResponse.BodyHandler.class));
    }

    @Test
    void authorization_error_is_not_retried() throws Exception {
        HttpResponse<String> failure = response(401, "unauthorized");
        when(client.send(any(), any(HttpResponse.BodyHandler.class))).thenReturn(failure);
        assertThatThrownBy(() -> service.analyze(prompt)).isInstanceOf(GmsAnalysisException.class);
        verify(client).send(any(), any(HttpResponse.BodyHandler.class));
    }

    @Test
    void timeouts_and_io_failures_stop_at_the_configured_attempt_limit() throws Exception {
        when(client.send(any(), any(HttpResponse.BodyHandler.class)))
                .thenThrow(new HttpTimeoutException("timeout"), new IOException("connection lost"));
        assertThatThrownBy(() -> service.analyze(prompt)).isInstanceOf(GmsAnalysisException.class)
                .hasMessageContaining("2 attempts");
        verify(client, times(2)).send(any(), any(HttpResponse.BodyHandler.class));
    }

    @ParameterizedTest
    @ValueSource(strings = {"not-json", "[]", "{}", "{\"choices\":[]}", "{\"choices\":[1]}",
            "{\"choices\":[{\"message\":{}}]}", "{\"choices\":[{\"message\":{\"content\":\" \"}}]}"})
    void rejects_invalid_gms_envelopes(String body) throws Exception {
        HttpResponse<String> invalid = response(200, body);
        when(client.send(any(), any(HttpResponse.BodyHandler.class))).thenReturn(invalid);
        assertThatThrownBy(() -> service.analyze(prompt)).isInstanceOf(GmsAnalysisException.class);
        verify(client).send(any(), any(HttpResponse.BodyHandler.class));
    }

    @Test
    void interruption_is_preserved_and_not_retried() throws Exception {
        when(client.send(any(), any(HttpResponse.BodyHandler.class))).thenThrow(new InterruptedException("stopped"));
        try {
            assertThatThrownBy(() -> service.analyze(prompt)).isInstanceOf(GmsAnalysisException.class);
            assertThat(Thread.currentThread().isInterrupted()).isTrue();
            verify(client).send(any(), any(HttpResponse.BodyHandler.class));
        } finally {
            Thread.interrupted();
        }
    }

    private String envelope() {
        return mapper.writeValueAsString(Map.of("choices", List.of(Map.of("message", Map.of("content", CONTENT)))));
    }

    @SuppressWarnings("unchecked")
    private HttpResponse<String> response(int status, String body) {
        HttpResponse<String> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(status);
        when(response.body()).thenReturn(body);
        return response;
    }

    private String requestBody(HttpRequest request) throws Exception {
        var done = new CompletableFuture<String>();
        request.bodyPublisher().orElseThrow().subscribe(new Flow.Subscriber<ByteBuffer>() {
            private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            public void onSubscribe(Flow.Subscription subscription) { subscription.request(Long.MAX_VALUE); }
            public void onNext(ByteBuffer buffer) {
                byte[] chunk = new byte[buffer.remaining()];
                buffer.get(chunk);
                bytes.writeBytes(chunk);
            }
            public void onError(Throwable error) { done.completeExceptionally(error); }
            public void onComplete() { done.complete(bytes.toString(StandardCharsets.UTF_8)); }
        });
        return done.get(1, TimeUnit.SECONDS);
    }
}
