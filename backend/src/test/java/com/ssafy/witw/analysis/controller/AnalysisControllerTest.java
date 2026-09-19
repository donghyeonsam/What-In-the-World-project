package com.ssafy.witw.analysis.controller;

import com.ssafy.witw.analysis.dto.IssueCountryAnalysisDetailResponse;
import com.ssafy.witw.analysis.dto.IssueCountryAnalysisListResponse;
import com.ssafy.witw.analysis.service.AnalysisService;
import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.security.config.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = AnalysisController.class)
@Import(SecurityConfig.class)
class AnalysisControllerTest {
    private static final LocalDateTime AS_OF = LocalDateTime.of(2026, 9, 18, 10, 0);
    private static final OffsetDateTime WINDOW_END = OffsetDateTime.parse("2026-09-18T09:00:00+09:00");

    @Autowired MockMvc mvc;
    @MockitoBean AnalysisService analysisService;

    @Test
    void list_uses_kst_as_of_and_returns_common_response() throws Exception {
        when(analysisService.getCountryAnalyses(42L, AS_OF)).thenReturn(new IssueCountryAnalysisListResponse(42L,
                List.of(new IssueCountryAnalysisListResponse.CountryAnalysis(
                        7L, "KR", "제목", "요약", 15, WINDOW_END))));

        mvc.perform(get("/api/v1/global/issues/42/country-analyses")
                        .param("asOf", "2026-09-18T01:00:00Z"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data.issueId").value(42))
                .andExpect(jsonPath("$.data.countryAnalyses[0].analysisId").value(7))
                .andExpect(jsonPath("$.data.countryAnalyses[0].countryCode").value("KR"))
                .andExpect(jsonPath("$.data.countryAnalyses[0].summary").value("요약"))
                .andExpect(jsonPath("$.data.countryAnalyses[0].windowEnd").value("2026-09-18T09:00:00+09:00"));
        verify(analysisService).getCountryAnalyses(42L, AS_OF);
    }

    @Test
    void detail_normalizes_country_code_and_returns_details_array() throws Exception {
        when(analysisService.getCountryAnalysis(42L, "KR", AS_OF)).thenReturn(new IssueCountryAnalysisDetailResponse(
                new IssueCountryAnalysisDetailResponse.Analysis(
                        7L, 42L, "KR", "제목", "요약", List.of("관점 1", "관점 2"), 15, WINDOW_END)));

        mvc.perform(get("/api/v1/global/issues/42/country-analyses/kr")
                        .param("asOf", "2026-09-18T01:00:00Z"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.analysis.title").value("제목"))
                .andExpect(jsonPath("$.data.analysis.details[0]").value("관점 1"))
                .andExpect(jsonPath("$.data.analysis.details[1]").value("관점 2"));
        verify(analysisService).getCountryAnalysis(42L, "KR", AS_OF);
    }

    @Test
    void existing_issue_without_analysis_keeps_data_envelope() throws Exception {
        when(analysisService.getCountryAnalysis(eq(42L), eq("KR"), any(LocalDateTime.class)))
                .thenReturn(new IssueCountryAnalysisDetailResponse(null));

        mvc.perform(get("/api/v1/global/issues/42/country-analyses/KR"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").exists())
                .andExpect(jsonPath("$.data.analysis").doesNotExist());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/v1/global/issues/0/country-analyses",
            "/api/v1/global/issues/42/country-analyses/KOR",
            "/api/v1/global/issues/42/country-analyses/12",
            "/api/v1/global/issues/42/country-analyses?asOf=2026-09-18T10:00:00"
    })
    void invalid_input_is_rejected_before_service(String path) throws Exception {
        mvc.perform(get(path)).andExpect(status().isBadRequest());
        verifyNoInteractions(analysisService);
    }

    @Test
    void unknown_issue_is_not_found() throws Exception {
        when(analysisService.getCountryAnalyses(eq(99L), any(LocalDateTime.class)))
                .thenThrow(new GlobalException(ErrorCode.ENTITY_NOT_FOUND));

        mvc.perform(get("/api/v1/global/issues/99/country-analyses"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CO03"));
    }
}
