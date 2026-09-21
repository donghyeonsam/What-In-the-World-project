package com.ssafy.witw.analysis.controller;

import com.ssafy.witw.analysis.dto.IssueCountryAnalysisDetailResponse;
import com.ssafy.witw.analysis.dto.IssueCountryAnalysisListResponse;
import com.ssafy.witw.analysis.service.AnalysisService;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.common.time.QueryTime;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.OffsetDateTime;
import java.util.Locale;

@RestController
@RequiredArgsConstructor
@RequestMapping(value = "/api/v1/global/issues/{issueId}/country-analyses", produces = "application/json")
@Tag(name = "국가별 이슈 분석", description = "이슈별 국가 보도 관점 분석 결과 조회")
public class AnalysisController {

    private final AnalysisService analysisService;

    @GetMapping
    @Operation(summary = "이슈의 국가별 분석 목록 조회", description = "국가별로 조회 시점 이전의 최신 분석 제목과 요약을 반환합니다.")
    public ResponseEntity<BaseResponse<IssueCountryAnalysisListResponse>> getCountryAnalyses(
            @Parameter(description = "이슈 ID", example = "1") @PathVariable @Positive long issueId,
            @RequestParam(name = "asOf", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS,
                analysisService.getCountryAnalyses(issueId, QueryTime.resolve(asOf)));
    }

    @GetMapping("/{countryCode}")
    @Operation(summary = "이슈의 국가별 분석 상세 조회", description = "조회 시점 이전의 최신 분석을 반환합니다. 분석 결과가 없으면 analysis가 null입니다.")
    public ResponseEntity<BaseResponse<IssueCountryAnalysisDetailResponse>> getCountryAnalysis(
            @Parameter(description = "이슈 ID", example = "1") @PathVariable @Positive long issueId,
            @Parameter(description = "영문 두 자리 국가 코드 (대소문자 무관)", example = "KR")
            @PathVariable @Pattern(regexp = "[a-zA-Z]{2}") String countryCode,
            @RequestParam(name = "asOf", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS,
                analysisService.getCountryAnalysis(issueId, countryCode.toUpperCase(Locale.ROOT), QueryTime.resolve(asOf)));
    }
}
