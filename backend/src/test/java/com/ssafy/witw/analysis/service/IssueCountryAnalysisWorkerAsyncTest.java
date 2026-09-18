package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.config.IssueCountryAnalysisAsyncConfig;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisGmsService.GmsAnalysisException;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class IssueCountryAnalysisWorkerAsyncTest {
    @Test
    @Timeout(15)
    void a_single_async_worker_queues_the_next_target_and_survives_a_failed_request() throws Exception {
        var articles = mock(IssueCountryAnalysisArticleService.class);
        var prompts = mock(IssueCountryAnalysisPromptService.class);
        var gms = mock(IssueCountryAnalysisGmsService.class);
        var validator = mock(IssueCountryAnalysisResponseValidator.class);
        var results = mock(IssueCountryAnalysisResultService.class);
        var prompt = new PreparedPrompt("system", "user", List.of("a"), 10, 5);
        var result = new AnalysisResult("title", "summary", List.of("detail"));
        var firstStarted = new CountDownLatch(1);
        var releaseFirst = new CountDownLatch(1);
        var nextSaved = new CountDownLatch(1);
        var calls = new AtomicInteger();
        var workerThread = new AtomicReference<String>();
        when(prompts.prepare(anyLong(), anyString(), anyString(), anyString(), anyLong(), any(), any(), anyList()))
                .thenReturn(prompt);
        when(gms.analyze(prompt)).thenAnswer(call -> {
            workerThread.set(Thread.currentThread().getName());
            if (calls.incrementAndGet() == 1) {
                firstStarted.countDown();
                if (!releaseFirst.await(5, TimeUnit.SECONDS)) throw new AssertionError("test worker was not released");
                throw new GmsAnalysisException("simulated timeout");
            }
            return "response";
        });
        when(validator.validate("response")).thenReturn(result);
        when(results.save(any(), any(), eq(result), eq(List.of("a")))).thenAnswer(call -> {
            nextSaved.countDown();
            return 1L;
        });

        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(IssueCountryAnalysisAsyncConfig.class, IssueCountryAnalysisWorkerService.class);
            context.registerBean(IssueCountryAnalysisArticleService.class, () -> articles);
            context.registerBean(IssueCountryAnalysisPromptService.class, () -> prompts);
            context.registerBean(IssueCountryAnalysisGmsService.class, () -> gms);
            context.registerBean(IssueCountryAnalysisResponseValidator.class, () -> validator);
            context.registerBean(IssueCountryAnalysisResultService.class, () -> results);
            context.refresh();
            try {
                var executor = context.getBean("issueCountryAnalysisExecutor", ThreadPoolTaskExecutor.class);
                assertThat(executor.getCorePoolSize()).isEqualTo(1);
                assertThat(executor.getMaxPoolSize()).isEqualTo(1);
                var worker = context.getBean(IssueCountryAnalysisWorkerService.class);
                var first = new Target(1, "issue", "KR", "Korea", 10);
                var second = new Target(1, "issue", "JP", "Japan", 10);
                var end = LocalDateTime.of(2026, 9, 18, 14, 0);
                worker.analyze(first, end.minusHours(24), end);
                assertThat(firstStarted.await(5, TimeUnit.SECONDS)).isTrue();
                worker.analyze(second, end.minusHours(24), end);
                assertThat(executor.getThreadPoolExecutor().getQueue()).hasSize(1);
                assertThat(calls).hasValue(1);
                releaseFirst.countDown();
                assertThat(nextSaved.await(5, TimeUnit.SECONDS)).isTrue();
                assertThat(workerThread.get()).startsWith("issue-country-analysis-");
                verify(results).save(second, end, result, List.of("a"));
                verify(results, never()).save(eq(first), any(), any(), anyList());
            } finally {
                releaseFirst.countDown();
            }
        }
    }
}
