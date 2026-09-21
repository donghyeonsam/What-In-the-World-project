package com.ssafy.witw.domain.country.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.country.dto.CountryMainResponse;
import com.ssafy.witw.domain.country.service.CountryService;
import com.ssafy.witw.domain.theme.dto.PopularThemeResponse;
import com.ssafy.witw.domain.theme.service.ThemeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
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
@RequestMapping(value = "/api/v1/countries", produces = "application/json")
@Tag(name = "국가", description = "국가 대시보드 및 인기 테마 조회")
public class CountryController {
    private final CountryService countryService;
    private final ThemeService themeService;

    @GetMapping("/{countryCode}")
    @Operation(summary = "국가 대시보드 조회", description = "최근 24시간 수집 기사 수, 국가 순위, 국가별 핫이슈 TOP 5, 인기 테마, 국가 간 언급 비율을 반환합니다. todayArticleCount는 자정 기준이 아닌 최근 24시간 수집 기사 수입니다.")
    public ResponseEntity<BaseResponse<CountryMainResponse>> getCountryMain(
            @Parameter(description = "영문 두 자리 국가 코드 (대소문자 무관)", example = "KR")
            @PathVariable @Pattern(regexp = "[a-zA-Z]{2}") String countryCode,
            @RequestParam(name = "asOf", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS,
                countryService.getCountryMain(countryCode.toUpperCase(Locale.ROOT), QueryTime.resolve(asOf)));
    }

    @GetMapping("/{countryCode}/themes/popular")
    @Operation(summary = "국가별 인기 테마 조회", description = "인기 테마와 1시간 간격 기사 수 24개를 반환합니다. 기존 집계 기준에 따라 현재 시간대를 포함하는 24개 시간 구간을 사용합니다.")
    public ResponseEntity<BaseResponse<PopularThemeResponse>> getPopularThemes(
            @Parameter(description = "영문 두 자리 국가 코드 (대소문자 무관)", example = "KR")
            @PathVariable @Pattern(regexp = "[a-zA-Z]{2}") String countryCode,
            @Parameter(description = "인기 테마 개수 (1~10)") @RequestParam(defaultValue = "3") @Min(1) @Max(10) int limit,
            @RequestParam(name = "asOf", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS,
                themeService.getPopularThemes(countryCode.toUpperCase(Locale.ROOT), limit, QueryTime.resolve(asOf)));
    }
}
