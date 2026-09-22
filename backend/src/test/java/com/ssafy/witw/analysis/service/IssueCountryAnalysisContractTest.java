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
import java.util.stream.IntStream;

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
        List<?> payloadArticles = (List<?>) body.get("representativeArticles");
        for (int index = 0; index < prompt.representativeArticleIds().size(); index++) {
            String id = prompt.representativeArticleIds().get(index);
            ArticleForAnalysis original = articles.stream()
                    .filter(a -> a.articleId().equals(id)).findFirst().orElseThrow();
            Map<?, ?> payloadArticle = (Map<?, ?>) payloadArticles.get(index);
            assertThat(payloadArticle.get("title")).isEqualTo(original.title());
            assertThat(payloadArticle.containsKey("id")).isFalse();
            assertThat(payloadArticle.containsKey("articleId")).isFalse();
            assertThat(prompt.userMessage()).doesNotContain(id);
        }
        assertThat(prompt.userMessage()).doesNotContain("representativeArticleIds", "evidenceArticleIds");
        assertThatThrownBy(() -> prompt.representativeArticleIds().add("extra"))
                .isInstanceOf(UnsupportedOperationException.class);
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
    void 첫_분석은_요약과_논조가_없는_기사_한_건으로도_프롬프트를_만든다() throws Exception {
        ArticleForAnalysis article = new ArticleForAnalysis("single", "기사 제목", null, null,
                "매체A", PERIOD_START.plusHours(1), BigDecimal.ONE);

        PreparedPrompt prompt = promptService.prepareInitial(56, "구체적인 이슈", "KR", "대한민국", 1,
                PERIOD_START, PERIOD_END, List.of(article));

        assertThat(prompt.usableArticleCount()).isEqualTo(1);
        assertThat(prompt.representativeArticleIds()).containsExactly("single");
        Map<?, ?> body = objectMapper.readValue(prompt.userMessage(), Map.class);
        Map<?, ?> evidence = (Map<?, ?>) ((List<?>) body.get("representativeArticles")).getFirst();
        assertThat(evidence.get("title")).isEqualTo("기사 제목");
        assertThat(evidence.get("summary")).isEqualTo("");
        assertThat(evidence.get("toneScore")).isNull();
        assertThat(prompt.systemMessage()).contains("근거 기사가 적거나");
        assertThatThrownBy(() -> prepare(List.of(article))).isInstanceOf(InsufficientArticlesException.class);
    }

    @Test
    void 첫_분석도_근거_기사가_전혀_없으면_건너뛴다() {
        assertThatThrownBy(() -> promptService.prepareInitial(56, "구체적인 이슈", "KR", "대한민국", 0,
                PERIOD_START, PERIOD_END, List.of())).isInstanceOf(InsufficientArticlesException.class);
    }

    @Test
    void 응답은_세_필드만_허용하고_근거_기사_ID를_받지_않는다() {
        String valid = """
                {"title":"보도 관점","summary":"서로 다른 보도 관점이 나타납니다.",
                 "details":["첫 번째 쟁점","두 번째 쟁점"]}
                """;

        var result = responseValidator.validate(valid);
        assertThat(result.details()).containsExactly("첫 번째 쟁점", "두 번째 쟁점");
        assertThatThrownBy(() -> responseValidator.validate(valid.replace("\"title\":", "\"evidenceArticleIds\":[\"id-1\"],\"title\":")))
                .isInstanceOf(InvalidAnalysisResponseException.class);
        assertThatThrownBy(() -> responseValidator.validate(valid.replace("\"title\":", "\"extra\":1,\"title\":")))
                .isInstanceOf(InvalidAnalysisResponseException.class);
        assertThatThrownBy(() -> responseValidator.validate("not JSON"))
                .isInstanceOf(InvalidAnalysisResponseException.class);
    }

    private PreparedPrompt prepare(List<ArticleForAnalysis> articles) {
        return promptService.prepare(56, "구체적인 이슈", "KR", "대한민국", articles.size(),
                PERIOD_START, PERIOD_END, articles);
    }

    @Test
    void invalid_articles_are_filtered_and_period_start_is_inclusive() {
        List<ArticleForAnalysis> articles = new ArrayList<>(validArticles());
        articles.add(null);
        articles.add(new ArticleForAnalysis(null, "null id", "summary", BigDecimal.TEN, null, PERIOD_START, null));
        articles.add(new ArticleForAnalysis(" ", "blank id", "summary", BigDecimal.TEN, null, PERIOD_START, null));
        articles.add(new ArticleForAnalysis("null-title", null, "summary", BigDecimal.TEN, null, PERIOD_START, null));
        articles.add(new ArticleForAnalysis("blank-title", " ", "summary", BigDecimal.TEN, null, PERIOD_START, null));
        articles.add(new ArticleForAnalysis("blank-summary", "title", " ", BigDecimal.TEN, null, PERIOD_START, null));
        articles.add(new ArticleForAnalysis("null-tone", "null tone", "summary", null, null, PERIOD_START, null));
        articles.add(new ArticleForAnalysis("null-time", "null time", "summary", BigDecimal.TEN, null, null, null));
        articles.add(article("invalid-negative-tone", "invalid negative", null, -1, PERIOD_START));
        articles.add(article("invalid-high-tone", "invalid high", null, 101, PERIOD_START));
        PreparedPrompt prompt = prepare(articles);
        assertThat(prompt.usableArticleCount()).isEqualTo(5);
        assertThat(prompt.representativeArticleIds()).containsExactlyInAnyOrder("a0", "a1", "a2", "a3", "a4");
    }

    @Test
    void input_text_is_bounded_and_all_five_eligible_ids_are_retained() {
        List<ArticleForAnalysis> articles = new ArrayList<>(validArticles());
        articles.set(0, new ArticleForAnalysis("a0", "가".repeat(151), "나".repeat(401),
                BigDecimal.ZERO, null, PERIOD_START, null));
        PreparedPrompt prompt = prepare(articles);
        Map<?, ?> body = objectMapper.readValue(prompt.userMessage(), Map.class);
        List<?> payloadArticles = (List<?>) body.get("representativeArticles");
        Map<?, ?> longArticle = payloadArticles.stream().map(Map.class::cast)
                .filter(a -> a.get("title").toString().startsWith("가")).findFirst().orElseThrow();
        assertThat(longArticle.get("title")).isEqualTo("가".repeat(150));
        assertThat(longArticle.get("summary")).isEqualTo("나".repeat(400));
        assertThat(prompt.representativeArticleIds()).hasSize(5).contains("a0");
        assertThatThrownBy(() -> prepare(validArticles().subList(0, 4)))
                .isInstanceOf(InsufficientArticlesException.class);
    }

    private static List<ArticleForAnalysis> validArticles() {
        return IntStream.range(0, 5).mapToObj(i ->
                article("a" + i, "Title " + i, "publisher", i * 25, PERIOD_START.plusHours(i))).toList();
    }

    @Test
    void selection_balances_tone_using_the_same_ranges_as_the_prompt() {
        int[] scores = {90, 38, 35, 50, 90};
        List<ArticleForAnalysis> articles = IntStream.range(0, scores.length)
                .mapToObj(i -> new ArticleForAnalysis("tone-" + i, "Tone title " + i, "summary",
                        BigDecimal.valueOf(scores[i]), "same publisher", PERIOD_START,
                        BigDecimal.valueOf(scores.length - i)))
                .toList();
        assertThat(prepare(articles).representativeArticleIds().subList(0, 3))
                .containsExactly("tone-0", "tone-1", "tone-3");
    }

    private static ArticleForAnalysis article(
            String id, String title, String publisher, int tone, LocalDateTime publishedAt
    ) {
        return new ArticleForAnalysis(id, title, "기사 내용을 요약한 문장입니다.", BigDecimal.valueOf(tone),
                publisher, publishedAt, BigDecimal.ONE);
    }
}
