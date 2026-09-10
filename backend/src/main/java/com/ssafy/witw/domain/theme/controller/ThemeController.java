package com.ssafy.witw.domain.theme.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.theme.dto.FieldThemesResponse;
import com.ssafy.witw.domain.theme.dto.ThemeOverviewResponse;
import com.ssafy.witw.domain.theme.service.ThemeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Pattern;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;

@RestController
@RequiredArgsConstructor
@RequestMapping(value = "/api/v1/themes", produces = "application/json")
@Tag(name = "테마", description = "분야별 테마 목록 및 테마 개요 조회")
public class ThemeController {
    private final ThemeService themeService;

    @GetMapping("/by-field")
    @Operation(summary = "분야별 테마 목록 조회", description = "전체 국가의 최근 24시간 발행 기사 수를 집계합니다. 삭제 기사는 제외하며, 기사 없는 테마는 0건으로 반환합니다.")
    public ResponseEntity<BaseResponse<List<FieldThemesResponse>>> getThemesByField() {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, themeService.getThemesByField());
    }

    @GetMapping("/{themeId}/overview")
    @Operation(summary = "테마 개요 조회", description = "테마 정보, 주요 이슈와 대표 기사를 반환합니다.")
    public ResponseEntity<BaseResponse<ThemeOverviewResponse>> getThemeOverview(
            @Parameter(description = "테마 ID", example = "1") @PathVariable @Positive Long themeId,
            @Parameter(description = "주요 이슈 개수 (1~10)") @RequestParam(defaultValue = "3") @Min(1) @Max(10) int issueLimit,
            @Parameter(description = "대표 기사 개수 (1~10)") @RequestParam(defaultValue = "10") @Min(1) @Max(10) int articleLimit,
            @Parameter(description = "대표 기사 발행 국가 코드") @RequestParam(required = false) @Pattern(regexp = "[a-zA-Z]{2}") String countryCode) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS,
                themeService.getThemeOverview(themeId, issueLimit, articleLimit,
                        countryCode == null ? null : countryCode.toUpperCase(Locale.ROOT)));
    }
}
