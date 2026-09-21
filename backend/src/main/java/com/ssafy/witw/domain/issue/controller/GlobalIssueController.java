package com.ssafy.witw.domain.issue.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.issue.dto.GlobalIssueDetailResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse;
import com.ssafy.witw.domain.issue.service.IssueService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
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

@RestController
@RequiredArgsConstructor
@RequestMapping(value = "/api/v1/global/issues", produces = "application/json")
@Tag(name = "글로벌 이슈", description = "글로벌 이슈 순위 및 상세 조회")
public class GlobalIssueController {
    private final IssueService issueService;

    @GetMapping
    @Operation(summary = "글로벌 이슈 TOP 5 조회", description = "전체 수집 기사 수, 최근 24시간 수집 기사 수, 최신 계층형 점수 스냅샷의 이슈 TOP 5를 반환합니다.")
    public ResponseEntity<BaseResponse<GlobalIssueRankResponse>> getGlobalIssueRank(@RequestParam(name = "asOf", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, issueService.getGlobalIssueRank(QueryTime.resolve(asOf)));
    }

    @GetMapping("/{issueId}")
    @Operation(summary = "글로벌 이슈 상세 조회", description = "이슈 상세 정보와 국가별 논조를 반환합니다.")
    public ResponseEntity<BaseResponse<GlobalIssueDetailResponse>> getGlobalIssueDetail(
            @Parameter(description = "이슈 ID", example = "1") @PathVariable @Positive long issueId,
            @RequestParam(name = "asOf", required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, issueService.getGlobalIssueDetail(issueId, QueryTime.resolve(asOf)));
    }
}
