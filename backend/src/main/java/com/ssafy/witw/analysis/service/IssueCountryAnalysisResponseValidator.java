package com.ssafy.witw.analysis.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * GMS가 반환한 국가별 이슈 분석 결과를 검증한다.
 *
 * GMS는 title / summary / details 세 필드만 반환해야 한다.
 *
 * 기사 ID는 GMS가 반환하지 않는다.
 * 실제 분석에 사용한 대표 기사 ID는
 * PreparedPrompt가 Spring 내부에서 별도로 보관한다.
 */
@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisResponseValidator {

    /**
     * GMS가 반드시 반환해야 하는 정확한 필드 집합.
     *
     * 추가 필드나 누락 필드가 있으면 잘못된 응답으로 처리한다.
     */
    private static final Set<String> REQUIRED_FIELDS =
            Set.of(
                    "title",
                    "summary",
                    "details"
            );

    private final ObjectMapper objectMapper;

    /**
     * GMS의 message.content를 검증하고
     * 저장 가능한 AnalysisResult로 변환한다.
     */
    public AnalysisResult validate(
            String responseText
    ) {
        if (responseText == null
                || responseText.isBlank()) {
            throw new InvalidAnalysisResponseException(
                    "Analysis response is required"
            );
        }

        Object parsed;

        try {
            parsed = objectMapper.readValue(
                    responseText,
                    Object.class
            );
        } catch (JacksonException exception) {
            throw new InvalidAnalysisResponseException(
                    "Analysis response must be valid JSON",
                    exception
            );
        }

        /*
         * JSON 객체여야 하며,
         * title / summary / details 이외의 필드를
         * 추가하거나 누락해서는 안 된다.
         */
        if (!(parsed instanceof Map<?, ?> body)
                || !body.keySet().equals(REQUIRED_FIELDS)) {
            throw new InvalidAnalysisResponseException(
                    "Analysis response must contain exactly "
                            + "title, summary and details"
            );
        }

        /*
         * PromptService의 출력 규칙과 동일한 길이 기준으로 검증한다.
         */
        String title = requiredText(
                body.get("title"),
                "title",
                50
        );

        String summary = requiredText(
                body.get("summary"),
                "summary",
                200
        );

        List<String> details =
                requiredTextList(
                        body.get("details"),
                        "details",
                        1,
                        3,
                        80
                );

        return new AnalysisResult(
                title,
                summary,
                details
        );
    }

    /**
     * 문자열 배열 필드의 개수와 각 문자열의 유효성을 검사한다.
     */
    private static List<String> requiredTextList(
            Object value,
            String name,
            int minSize,
            int maxSize,
            int maxTextLength
    ) {
        if (!(value instanceof List<?> items)
                || items.size() < minSize
                || items.size() > maxSize) {
            throw new InvalidAnalysisResponseException(
                    name + " has an invalid item count"
            );
        }

        List<String> result =
                new ArrayList<>(
                        items.size()
                );

        for (Object item : items) {
            result.add(
                    requiredText(
                            item,
                            name,
                            maxTextLength
                    )
            );
        }

        return List.copyOf(result);
    }

    /**
     * 필수 문자열 값이 존재하고,
     * 공백이 아니며,
     * 최대 길이를 넘지 않는지 검증한다.
     */
    private static String requiredText(
            Object value,
            String name,
            int maxLength
    ) {
        if (!(value instanceof String text)
                || text.isBlank()
                || text.strip().length() > maxLength) {
            throw new InvalidAnalysisResponseException(
                    name + " is invalid"
            );
        }

        return text.strip();
    }

    /**
     * 검증이 끝난 최종 분석 결과.
     *
     * evidenceArticleIds는 포함하지 않는다.
     * 대표 기사 ID는 PreparedPrompt에 별도로 존재한다.
     */
    public record AnalysisResult(
            String title,
            String summary,
            List<String> details
    ) {
        public AnalysisResult {
            details = List.copyOf(details);
        }
    }

    public static class InvalidAnalysisResponseException
            extends RuntimeException {

        public InvalidAnalysisResponseException(
                String message
        ) {
            super(message);
        }

        public InvalidAnalysisResponseException(
                String message,
                Throwable cause
        ) {
            super(message, cause);
        }
    }
}
