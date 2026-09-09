package com.ssafy.witw.domain.issue.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.issue.dto.IssueOverviewResponse;
import com.ssafy.witw.domain.issue.service.IssueService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping(value = "/api/v1/issues", produces = "application/json")
@Tag(name = "이슈", description = "이슈 미리보기 조회")
public class IssueController {
    private final IssueService issueService;

    @GetMapping("/{issueId}/overview")
    @Operation(summary = "이슈 미리보기 조회", description = "이슈·테마 제목, 기사 수, 국가별 논조, 대표 기사를 반환합니다.")
    public ResponseEntity<BaseResponse<IssueOverviewResponse>> getIssueOverview(
            @Parameter(description = "이슈 ID", example = "1") @PathVariable @Positive long issueId,
            @Parameter(description = "대표 기사 개수 (1~10)") @RequestParam(defaultValue = "3") @Min(1) @Max(10) int articleLimit) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, issueService.getIssueOverview(issueId, articleLimit));
    }
}
