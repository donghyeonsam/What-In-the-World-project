package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.InvalidAnalysisResponseException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.json.JsonMapper;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class IssueCountryAnalysisResponseValidatorTest {
    private final JsonMapper mapper = JsonMapper.builder().build();
    private final IssueCountryAnalysisResponseValidator validator = new IssueCountryAnalysisResponseValidator(mapper);

    @Test
    void accepts_one_to_three_details_and_trims_values() {
        for (int count = 1; count <= 3; count++) {
            var result = validator.validate(json(" 제목 ", " 요약 ", java.util.Collections.nCopies(count, " 내용 ")));
            assertThat(result.title()).isEqualTo("제목");
            assertThat(result.summary()).isEqualTo("요약");
            assertThat(result.details()).hasSize(count).containsOnly("내용");
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"title", "summary", "details"})
    void rejects_missing_fields(String field) {
        Map<String, Object> body = new LinkedHashMap<>(Map.of("title", "t", "summary", "s", "details", List.of("d")));
        body.remove(field);
        assertInvalid(mapper.writeValueAsString(body));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "not JSON", "[]", "null", "{}", "{", "```json\n{}\n```",
            "{\"title\":1,\"summary\":\"s\",\"details\":[\"d\"]}",
            "{\"title\":\"t\",\"summary\":\"s\",\"details\":\"d\"}",
            "{\"title\":\"t\",\"summary\":\"s\",\"details\":[null]}",
            "{\"title\":\"t\",\"summary\":\"s\",\"details\":[12]}",
            "{\"title\":\"t\",\"summary\":\"s\",\"details\":[\"d\"],\"evidenceArticleIds\":[]}"})
    void rejects_invalid_json_and_types(String response) {
        assertInvalid(response);
    }

    @Test
    void enforces_the_prompt_length_limits() {
        var result = validator.validate(json("가".repeat(50), "나".repeat(200), List.of("다".repeat(80))));
        assertThat(result.title()).hasSize(50);
        assertInvalid(json("가".repeat(51), "s", List.of("d")));
        assertInvalid(json("t", "나".repeat(201), List.of("d")));
        assertInvalid(json("t", "s", List.of("다".repeat(81))));
    }

    @Test
    void rejects_empty_values_and_details_outside_one_to_three() {
        assertInvalid(json(" ", "s", List.of("d")));
        assertInvalid(json("t", " ", List.of("d")));
        assertInvalid(json("t", "s", List.of(" ")));
        assertInvalid(json("t", "s", List.of()));
        assertInvalid(json("t", "s", List.of("a", "b", "c", "d")));
    }

    @Test
    void rejects_multiple_json_documents() {
        String valid = json("t", "s", List.of("d"));
        assertInvalid(valid + " " + valid);
    }

    private String json(String title, String summary, List<String> details) {
        return mapper.writeValueAsString(Map.of("title", title, "summary", summary, "details", details));
    }

    private void assertInvalid(String response) {
        assertThatThrownBy(() -> validator.validate(response)).isInstanceOf(InvalidAnalysisResponseException.class);
    }
}
