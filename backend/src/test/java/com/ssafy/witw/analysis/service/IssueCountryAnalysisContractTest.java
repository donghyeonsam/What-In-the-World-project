package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisArticleRepository.ArticleForAnalysis;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.InsufficientArticlesException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.InvalidAnalysisResponseException;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class IssueCountryAnalysisContractTest {

    private static final LocalDateTime PERIOD_START = LocalDateTime.of(2026, 9, 17, 14, 0);
    private static final LocalDateTime PERIOD_END = PERIOD_START.plusHours(24);

    private final ObjectMapper objectMapper = JsonMapper.builder().findAndAddModules().build();
    private final IssueCountryAnalysisPromptService promptService =
            new IssueCountryAnalysisPromptService(objectMapper);
    private final IssueCountryAnalysisResponseValidator responseValidator =
            new IssueCountryAnalysisResponseValidator(objectMapper);

    @Test
    void 대표_기사는_요약과_제목을_검사하고_매체_논조_시간대를_분산한다() throws Exception {
        List<ArticleForAnalysis> articles = new ArrayList<>();
        for (int index = 0; index < 12; index++) {
            articles.add(article("positive-" + index, "긍정 기사 " + index, "매체A", 90,
                    PERIOD_END.minusMinutes(index + 1)));
        }
        for (int index = 0; index < 3; index++) {
            articles.add(article("negative-" + index, "부정 기사 " + index, "매체B", 10,
                    PERIOD_START.plusHours(index + 1)));
            articles.add(article("neutral-" + index, "중립 기사 " + index, "매체C", 50,
                    PERIOD_START.plusHours(index + 10)));
        }
        articles.add(new ArticleForAnalysis("no-summary", "제목", null, BigDecimal.TEN,
                "매체D", PERIOD_START.plusHours(1), BigDecimal.ONE));
        articles.add(article("before-window", "기간 전 기사", "매체E", 20,
                PERIOD_START.minusSeconds(1)));
        articles.add(article("at-end", "기간 후 기사", "매체F", 80, PERIOD_END));

        PreparedPrompt prompt = prepare(articles);

        assertThat(prompt.totalArticleCount()).isEqualTo(articles.size());
        assertThat(prompt.usableArticleCount()).isEqualTo(18);
        assertThat(prompt.representativeArticleIds()).hasSize(12)
                .anyMatch(id -> id.startsWith("positive-"))
                .anyMatch(id -> id.startsWith("negative-"))
                .anyMatch(id -> id.startsWith("neutral-"))
                .doesNotContain("no-summary", "before-window", "at-end");
        assertThat(prompt.systemMessage()).contains("외부 자료");
        Map<?, ?> body = objectMapper.readValue(prompt.userMessage(), Map.class);
        assertThat(body.get("totalArticleCount")).isEqualTo(articles.size());
        assertThat((List<?>) body.get("representativeArticles")).hasSize(12);
    }

    @Test
    void 같은_제목은_한_번만_사용하고_요약_가능_기사가_부족하면_건너뛴다() {
        List<ArticleForAnalysis> articles = new ArrayList<>();
        for (int index = 0; index < 4; index++) {
            articles.add(article("id-" + index, "제목 " + index, "매체A", 50,
                    PERIOD_START.plusHours(index + 1)));
        }
        articles.add(article("duplicate", "  제목   0  ", "매체B", 30,
                PERIOD_START.plusHours(6)));

        assertThatThrownBy(() -> prepare(articles)).isInstanceOf(InsufficientArticlesException.class);

        articles.add(article("fifth", "다른 제목", "매체C", 80, PERIOD_START.plusHours(7)));
        PreparedPrompt prompt = prepare(articles);
        assertThat(prompt.usableArticleCount()).isEqualTo(5);
        assertThat(prompt.representativeArticleIds()).hasSize(5);
        assertThat(prompt.representativeArticleIds().stream()
                .filter(id -> id.equals("id-0") || id.equals("duplicate")).count()).isEqualTo(1);
    }

    @Test
    void 응답은_정해진_JSON_형식과_입력에_포함된_근거_기사만_허용한다() {
        PreparedPrompt prompt = prepare(List.of(
                article("id-1", "제목 1", "매체A", 10, PERIOD_START.plusHours(1)),
                article("id-2", "제목 2", "매체B", 30, PERIOD_START.plusHours(2)),
                article("id-3", "제목 3", "매체C", 50, PERIOD_START.plusHours(3)),
                article("id-4", "제목 4", "매체D", 70, PERIOD_START.plusHours(4)),
                article("id-5", "제목 5", "매체E", 90, PERIOD_START.plusHours(5))));
        String valid = """
                {"title":"보도 관점","summary":"서로 다른 보도 관점이 나타납니다.",
                 "details":["첫 번째 쟁점","두 번째 쟁점"],
                 "evidenceArticleIds":["id-1","id-3"]}
                """;

        var result = responseValidator.validate(valid, prompt);
        assertThat(result.evidenceArticleIds()).containsExactly("id-1", "id-3");
        assertThat(result.details()).containsExactly("첫 번째 쟁점", "두 번째 쟁점");
        assertThatThrownBy(() -> responseValidator.validate(valid.replace("id-3", "unknown"), prompt))
                .isInstanceOf(InvalidAnalysisResponseException.class);
        assertThatThrownBy(() -> responseValidator.validate(valid.replace("id-3", "id-1"), prompt))
                .isInstanceOf(InvalidAnalysisResponseException.class);
        assertThatThrownBy(() -> responseValidator.validate(valid.replace("\"title\":", "\"extra\":1,\"title\":"), prompt))
                .isInstanceOf(InvalidAnalysisResponseException.class);
        assertThatThrownBy(() -> responseValidator.validate("not JSON", prompt))
                .isInstanceOf(InvalidAnalysisResponseException.class);
    }

    private PreparedPrompt prepare(List<ArticleForAnalysis> articles) {
        return promptService.prepare(56, "구체적인 이슈", "KR", "대한민국", articles.size(),
                PERIOD_START, PERIOD_END, articles);
    }

    private static ArticleForAnalysis article(
            String id, String title, String publisher, int tone, LocalDateTime publishedAt
    ) {
        return new ArticleForAnalysis(id, title, "기사 내용을 요약한 문장입니다.", BigDecimal.valueOf(tone),
                publisher, publishedAt, BigDecimal.ONE);
    }
}
