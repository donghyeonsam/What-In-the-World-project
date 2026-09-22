package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisQueryRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisQueryRepository.AnalysisRow;
import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

class AnalysisServiceImplTest {
    private static final long ISSUE_ID = 42L;
    private static final LocalDateTime AS_OF = LocalDateTime.of(2026, 9, 19, 14, 30);
    private static final LocalDateTime WINDOW_END = AS_OF.minusMinutes(30);

    private IssueCountryAnalysisQueryRepository repository;
    private AnalysisServiceImpl service;

    @BeforeEach
    void setUp() {
        repository = mock(IssueCountryAnalysisQueryRepository.class);
        service = new AnalysisServiceImpl(repository, JsonMapper.builder().build());
        when(repository.issueExistsAt(ISSUE_ID, AS_OF)).thenReturn(true);
    }

    @Test
    void list_returns_lightweight_latest_country_analyses() {
        when(repository.findLatestByIssue(ISSUE_ID, AS_OF)).thenReturn(List.of(row(1, "KR"), row(2, "US")));

        var response = service.getCountryAnalyses(ISSUE_ID, AS_OF);

        assertThat(response.issueId()).isEqualTo(ISSUE_ID);
        assertThat(response.countryAnalyses()).hasSize(2);
        assertThat(response.countryAnalyses().getFirst().countryCode()).isEqualTo("KR");
        assertThat(response.countryAnalyses().getFirst().title()).isEqualTo("제목");
        assertThat(response.countryAnalyses().getFirst().summary()).isEqualTo("요약");
        assertThat(response.countryAnalyses().getFirst().articleCount()).isEqualTo(15);
        assertThat(response.countryAnalyses().getFirst().windowEnd().getOffset()).isEqualTo(ZoneOffset.ofHours(9));
        assertThat(response.countryAnalyses().getFirst().windowEnd().toLocalDateTime()).isEqualTo(WINDOW_END);
    }

    @Test
    void detail_parses_json_array_and_preserves_window_end() {
        when(repository.findLatestByIssueAndCountry(ISSUE_ID, "KR", AS_OF)).thenReturn(Optional.of(row(1, "KR")));

        var analysis = service.getCountryAnalysis(ISSUE_ID, "KR", AS_OF).analysis();

        assertThat(analysis.analysisId()).isEqualTo(1);
        assertThat(analysis.issueId()).isEqualTo(ISSUE_ID);
        assertThat(analysis.details()).containsExactly("관점 1", "관점 2");
        assertThat(analysis.windowEnd().toLocalDateTime()).isEqualTo(WINDOW_END);
    }

    @Test
    void existing_issue_without_analysis_is_a_normal_empty_result() {
        when(repository.findLatestByIssue(ISSUE_ID, AS_OF)).thenReturn(List.of());
        when(repository.findLatestByIssueAndCountry(ISSUE_ID, "KR", AS_OF)).thenReturn(Optional.empty());

        assertThat(service.getCountryAnalyses(ISSUE_ID, AS_OF).countryAnalyses()).isEmpty();
        assertThat(service.getCountryAnalysis(ISSUE_ID, "KR", AS_OF).analysis()).isNull();
    }

    @Test
    void unknown_or_not_yet_created_issue_is_not_found() {
        when(repository.issueExistsAt(ISSUE_ID, AS_OF)).thenReturn(false);

        assertThatThrownBy(() -> service.getCountryAnalyses(ISSUE_ID, AS_OF))
                .isInstanceOfSatisfying(GlobalException.class,
                        error -> assertThat(error.getErrorCode()).isEqualTo(ErrorCode.ENTITY_NOT_FOUND));
        assertThatThrownBy(() -> service.getCountryAnalysis(ISSUE_ID, "KR", AS_OF))
                .isInstanceOf(GlobalException.class);
        verify(repository, org.mockito.Mockito.times(2)).issueExistsAt(ISSUE_ID, AS_OF);
        verifyNoMoreInteractions(repository);
    }

    @Test
    void corrupt_stored_details_are_not_silently_exposed() {
        var corrupt = new AnalysisRow(1, ISSUE_ID, "KR", "제목", "요약", "[1]", 15, WINDOW_END);
        when(repository.findLatestByIssueAndCountry(ISSUE_ID, "KR", AS_OF)).thenReturn(Optional.of(corrupt));

        assertThatThrownBy(() -> service.getCountryAnalysis(ISSUE_ID, "KR", AS_OF))
                .isInstanceOf(IllegalStateException.class);
        verify(repository).findLatestByIssueAndCountry(ISSUE_ID, "KR", AS_OF);
    }

    private AnalysisRow row(long id, String countryCode) {
        return new AnalysisRow(id, ISSUE_ID, countryCode, "제목", "요약", "[\"관점 1\",\"관점 2\"]", 15, WINDOW_END);
    }
}
