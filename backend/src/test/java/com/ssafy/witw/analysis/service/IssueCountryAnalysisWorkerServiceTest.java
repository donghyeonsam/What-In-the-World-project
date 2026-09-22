package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisArticleRepository.ArticleForAnalysis;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisQueryRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisGmsService.GmsAnalysisException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.InsufficientArticlesException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.InvalidAnalysisResponseException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class IssueCountryAnalysisWorkerServiceTest {
    private static final LocalDateTime END = LocalDateTime.of(2026, 9, 18, 14, 0);
    private static final LocalDateTime START = END.minusHours(24);
    private static final Target TARGET = new Target(1, "이슈", "KR", "대한민국", 10);
    private static final PreparedPrompt PROMPT = new PreparedPrompt("system", "user", List.of("a", "b"), 10, 5);
    private static final AnalysisResult RESULT = new AnalysisResult("제목", "요약", List.of("관점"));

    @Mock IssueCountryAnalysisArticleService articles;
    @Mock IssueCountryAnalysisQueryRepository analysisQueryRepository;
    @Mock IssueCountryAnalysisPromptService prompts;
    @Mock IssueCountryAnalysisGmsService gms;
    @Mock IssueCountryAnalysisResponseValidator validator;
    @Mock IssueCountryAnalysisResultService results;
    @InjectMocks IssueCountryAnalysisWorkerService worker;

    @Test
    void follows_the_complete_pipeline_and_preserves_window_and_evidence() {
        priorAnalysisExists();
        List<ArticleForAnalysis> input = List.of();
        when(articles.findArticles(1, "KR", START, END)).thenReturn(input);
        when(prompts.prepare(1, "이슈", "KR", "대한민국", 10, START, END, input)).thenReturn(PROMPT);
        when(gms.analyze(PROMPT)).thenReturn("response");
        when(validator.validate("response")).thenReturn(RESULT);
        worker.analyze(TARGET, START, END);
        var order = inOrder(articles, analysisQueryRepository, prompts, gms, validator, results);
        order.verify(articles).findArticles(1, "KR", START, END);
        order.verify(analysisQueryRepository).analysisExistsAt(1, "KR", END);
        order.verify(prompts).prepare(1, "이슈", "KR", "대한민국", 10, START, END, input);
        order.verify(gms).analyze(PROMPT);
        order.verify(validator).validate("response");
        order.verify(results).save(TARGET, END, RESULT, PROMPT.representativeArticleIds());
        order.verifyNoMoreInteractions();
    }

    @Test
    void insufficient_articles_skip_only_this_target() {
        priorAnalysisExists();
        when(prompts.prepare(anyLong(), anyString(), anyString(), anyString(), anyLong(), any(), any(), anyList()))
                .thenThrow(new InsufficientArticlesException("not enough articles"));
        assertThatCode(() -> worker.analyze(TARGET, START, END)).doesNotThrowAnyException();
        verifyNoInteractions(gms, validator, results);
    }

    @Test
    void a_gms_failure_does_not_prevent_the_next_target_from_saving() {
        priorAnalysisExists();
        stubPrompt();
        when(gms.analyze(PROMPT)).thenThrow(new GmsAnalysisException("timeout")).thenReturn("ok");
        when(validator.validate("ok")).thenReturn(RESULT);
        Target next = new Target(1, "이슈", "JP", "일본", 12);
        assertThatCode(() -> worker.analyze(TARGET, START, END)).doesNotThrowAnyException();
        verifyNoInteractions(validator, results);
        worker.analyze(next, START, END);
        verify(results).save(next, END, RESULT, PROMPT.representativeArticleIds());
    }

    @Test
    void invalid_gms_json_is_not_saved() {
        priorAnalysisExists();
        stubPrompt();
        when(gms.analyze(PROMPT)).thenReturn("invalid");
        when(validator.validate("invalid")).thenThrow(new InvalidAnalysisResponseException("invalid JSON"));
        assertThatCode(() -> worker.analyze(TARGET, START, END)).doesNotThrowAnyException();
        verifyNoInteractions(results);
    }

    @Test
    void storage_failure_does_not_escape_the_worker() {
        priorAnalysisExists();
        stubPrompt();
        when(gms.analyze(PROMPT)).thenReturn("ok");
        when(validator.validate("ok")).thenReturn(RESULT);
        when(results.save(TARGET, END, RESULT, PROMPT.representativeArticleIds()))
                .thenThrow(new DataIntegrityViolationException("evidence FK"));
        assertThatCode(() -> worker.analyze(TARGET, START, END)).doesNotThrowAnyException();
        verify(results).save(TARGET, END, RESULT, PROMPT.representativeArticleIds());
    }

    private void stubPrompt() {
        when(prompts.prepare(anyLong(), anyString(), anyString(), anyString(), anyLong(), any(), any(), anyList()))
                .thenReturn(PROMPT);
    }

    @Test
    void first_analysis_uses_the_initial_prompt_with_one_article() {
        Target first = new Target(1, "이슈", "MX", "멕시코", 1);
        List<ArticleForAnalysis> input = List.of(new ArticleForAnalysis(
                "one", "기사 제목", null, null, "매체", START.plusHours(1), null));
        PreparedPrompt initial = new PreparedPrompt("system", "user", List.of("one"), 1, 1);
        when(articles.findArticles(1, "MX", START, END)).thenReturn(input);
        when(prompts.prepareInitial(1, "이슈", "MX", "멕시코", 1, START, END, input)).thenReturn(initial);
        when(gms.analyze(initial)).thenReturn("response");
        when(validator.validate("response")).thenReturn(RESULT);

        worker.analyze(first, START, END);

        verify(analysisQueryRepository).analysisExistsAt(1, "MX", END);
        verify(prompts).prepareInitial(1, "이슈", "MX", "멕시코", 1, START, END, input);
        verify(prompts, never()).prepare(anyLong(), anyString(), anyString(), anyString(), anyLong(), any(), any(), anyList());
        verify(results).save(first, END, RESULT, List.of("one"));
    }

    private void priorAnalysisExists() {
        when(analysisQueryRepository.analysisExistsAt(anyLong(), anyString(), any())).thenReturn(true);
    }
}
