package com.ssafy.witw.analysis.scheduler;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisTargetService;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisWorkerService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.task.TaskRejectedException;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class IssueCountryAnalysisSchedulerTest {
    private final IssueCountryAnalysisTargetService targets = mock(IssueCountryAnalysisTargetService.class);
    private final IssueCountryAnalysisWorkerService worker = mock(IssueCountryAnalysisWorkerService.class);
    private final IssueCountryAnalysisScheduler scheduler = new IssueCountryAnalysisScheduler(targets, worker);
    private final Target first = new Target(1, "issue", "KR", "Korea", 10);
    private final Target second = new Target(1, "issue", "JP", "Japan", 12);

    @Test
    void dispatches_every_target_using_one_seoul_timestamp_and_a_24_hour_window() {
        when(targets.findTargets(any(), any())).thenReturn(List.of(first, second));
        LocalDateTime before = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        scheduler.runAnalysis();
        LocalDateTime after = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        ArgumentCaptor<LocalDateTime> start = ArgumentCaptor.forClass(LocalDateTime.class);
        ArgumentCaptor<LocalDateTime> end = ArgumentCaptor.forClass(LocalDateTime.class);
        verify(targets).findTargets(start.capture(), end.capture());
        assertThat(end.getValue()).isBetween(before, after);
        assertThat(Duration.between(start.getValue(), end.getValue())).isEqualTo(Duration.ofHours(24));
        verify(worker).analyze(first, start.getValue(), end.getValue());
        verify(worker).analyze(second, start.getValue(), end.getValue());
        verifyNoMoreInteractions(worker);
    }

    @Test
    void empty_targets_do_not_start_a_worker() {
        when(targets.findTargets(any(), any())).thenReturn(List.of());
        scheduler.runAnalysis();
        verifyNoInteractions(worker);
    }

    @Test
    void disabled_scheduler_is_not_registered() {
        new ApplicationContextRunner().withUserConfiguration(IssueCountryAnalysisScheduler.class)
                .withBean(IssueCountryAnalysisTargetService.class, () -> targets)
                .withBean(IssueCountryAnalysisWorkerService.class, () -> worker)
                .withPropertyValues("analysis.scheduler.enabled=false")
                .run(context -> assertThat(context).doesNotHaveBean(IssueCountryAnalysisScheduler.class));
        verifyNoInteractions(targets, worker);
    }

    @Test
    void rejected_submission_does_not_abort_remaining_targets() {
        when(targets.findTargets(any(), any())).thenReturn(List.of(first, second));
        doThrow(new TaskRejectedException("queue full")).when(worker).analyze(eq(first), any(), any());
        assertThatCode(scheduler::runAnalysis).doesNotThrowAnyException();
        verify(worker).analyze(eq(second), any(), any());
    }
}
