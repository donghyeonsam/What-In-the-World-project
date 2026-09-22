package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisArticleRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.LocalDateTime;

import static org.mockito.Mockito.*;

class IssueCountryAnalysisQueryServiceTest {
    private static final LocalDateTime END = LocalDateTime.of(2026, 9, 18, 14, 0);
    private static final LocalDateTime START = END.minusHours(24);

    @Test
    void defaults_to_top_five_and_ten_articles() {
        var repository = mock(IssueCountryAnalysisTargetRepository.class);
        new IssueCountryAnalysisTargetService(repository).findTargets(START, END);
        verify(repository).findTargets(START, END, 5, 10);
    }

    @Test
    void configured_top_n_and_minimum_are_forwarded() {
        var repository = mock(IssueCountryAnalysisTargetRepository.class);
        var service = new IssueCountryAnalysisTargetService(repository);
        ReflectionTestUtils.setField(service, "topIssueLimit", 10);
        ReflectionTestUtils.setField(service, "minCountryArticleCount", 20);
        service.findTargets(START, END);
        verify(repository).findTargets(START, END, 10, 20);
    }

    @Test
    void article_service_preserves_issue_country_and_window() {
        var repository = mock(IssueCountryAnalysisArticleRepository.class);
        new IssueCountryAnalysisArticleService(repository).findArticles(1, "KR", START, END);
        verify(repository).findArticles(1, "KR", START, END);
    }
}
