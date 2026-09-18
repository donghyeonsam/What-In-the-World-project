package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisResultRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.json.JsonMapper;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class IssueCountryAnalysisResultServiceTest {
    private static final Target TARGET = new Target(1, "이슈", "KR", "대한민국", 100);
    private static final LocalDateTime END = LocalDateTime.of(2026, 9, 18, 14, 0);
    private final JsonMapper mapper = JsonMapper.builder().build();
    private final IssueCountryAnalysisResultRepository repository = mock(IssueCountryAnalysisResultRepository.class);
    private final IssueCountryAnalysisResultService service = new IssueCountryAnalysisResultService(repository, mapper);
    private final AnalysisResult result = new AnalysisResult("제목", "요약", List.of("인용: \"관점\"", "다른 관점\n줄바꿈"));

    @Test
    void stores_details_as_json_and_all_representatives_with_the_same_analysis_id() {
        List<String> ids = IntStream.range(0, 12).mapToObj(i -> "article-" + i).toList();
        when(repository.insertAnalysis(anyLong(), anyString(), anyString(), anyString(), anyString(), anyLong(), any()))
                .thenReturn(123L);
        assertThat(service.save(TARGET, END, result, ids)).isEqualTo(123L);
        var order = inOrder(repository);
        ArgumentCaptor<String> details = ArgumentCaptor.forClass(String.class);
        order.verify(repository).insertAnalysis(eq(1L), eq("KR"), eq("제목"), eq("요약"), details.capture(), eq(100L), eq(END));
        order.verify(repository).insertEvidence(123, ids);
        assertThat(mapper.readValue(details.getValue(), List.class)).isEqualTo(result.details());
        order.verifyNoMoreInteractions();
    }

    @Test
    void trims_and_deduplicates_evidence_ids() {
        when(repository.insertAnalysis(anyLong(), anyString(), anyString(), anyString(), anyString(), anyLong(), any()))
                .thenReturn(123L);
        service.save(TARGET, END, result, Arrays.asList(" a ", "a", "b", " ", null));
        verify(repository).insertEvidence(123, List.of("a", "b"));
    }

    @Test
    void rejects_empty_or_invalid_evidence_before_writing() {
        assertThatThrownBy(() -> service.save(TARGET, END, result, List.of())).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.save(TARGET, END, result, Arrays.asList(null, " ")))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.save(TARGET, END, result, null)).isInstanceOf(NullPointerException.class);
        verifyNoInteractions(repository);
    }
}
