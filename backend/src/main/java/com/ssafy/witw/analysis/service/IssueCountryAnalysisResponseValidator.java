package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisResponseValidator {

    private static final Set<String> REQUIRED_FIELDS =
            Set.of("title", "summary", "details", "evidenceArticleIds");

    private final ObjectMapper objectMapper;

    public AnalysisResult validate(String responseText, PreparedPrompt prompt) {
        if (responseText == null || responseText.isBlank() || prompt == null) {
            throw new InvalidAnalysisResponseException("Analysis response and prompt are required");
        }

        Object parsed;
        try {
            parsed = objectMapper.readValue(responseText, Object.class);
        } catch (JacksonException exception) {
            throw new InvalidAnalysisResponseException("Analysis response must be valid JSON", exception);
        }
        if (!(parsed instanceof Map<?, ?> body) || !body.keySet().equals(REQUIRED_FIELDS)) {
            throw new InvalidAnalysisResponseException("Analysis response has unexpected fields");
        }

        String title = requiredText(body.get("title"), "title", 100);
        String summary = requiredText(body.get("summary"), "summary", 400);
        List<String> details = requiredTextList(body.get("details"), "details", 1, 4, 300);
        List<String> evidenceIds = requiredTextList(
                body.get("evidenceArticleIds"), "evidenceArticleIds", 1, 5, 255);
        Set<String> uniqueEvidenceIds = new HashSet<>(evidenceIds);
        if (uniqueEvidenceIds.size() != evidenceIds.size()
                || !prompt.representativeArticleIds().containsAll(uniqueEvidenceIds)) {
            throw new InvalidAnalysisResponseException("Evidence IDs must be distinct input article IDs");
        }
        return new AnalysisResult(title, summary, details, evidenceIds);
    }

    private static List<String> requiredTextList(
            Object value, String name, int minSize, int maxSize, int maxTextLength
    ) {
        if (!(value instanceof List<?> items) || items.size() < minSize || items.size() > maxSize) {
            throw new InvalidAnalysisResponseException(name + " has an invalid item count");
        }
        List<String> result = new ArrayList<>(items.size());
        for (Object item : items) {
            result.add(requiredText(item, name, maxTextLength));
        }
        return List.copyOf(result);
    }

    private static String requiredText(Object value, String name, int maxLength) {
        if (!(value instanceof String text) || text.isBlank() || text.strip().length() > maxLength) {
            throw new InvalidAnalysisResponseException(name + " is invalid");
        }
        return text.strip();
    }

    public record AnalysisResult(
            String title,
            String summary,
            List<String> details,
            List<String> evidenceArticleIds
    ) {
        public AnalysisResult {
            details = List.copyOf(details);
            evidenceArticleIds = List.copyOf(evidenceArticleIds);
        }
    }

    public static class InvalidAnalysisResponseException extends RuntimeException {
        public InvalidAnalysisResponseException(String message) {
            super(message);
        }

        public InvalidAnalysisResponseException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
