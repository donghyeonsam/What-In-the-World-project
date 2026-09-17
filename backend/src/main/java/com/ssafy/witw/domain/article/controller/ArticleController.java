package com.ssafy.witw.domain.article.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.article.dto.ArticleDetailResponse;
import com.ssafy.witw.domain.article.dto.ArticleFiltersResponse;
import com.ssafy.witw.domain.article.dto.ArticlePageResponse;
import com.ssafy.witw.domain.article.service.ArticleNewsService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
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

import java.time.LocalDate;
import java.time.OffsetDateTime;

/** Copy to the existing ArticleController.java path when integrating; do not add a second controller. */
@RestController
@RequiredArgsConstructor
@RequestMapping(value = "/api/v1/articles", produces = "application/json")
public class ArticleController {
    private final ArticleNewsService articleNewsService;

    @GetMapping("/filters")
    public ResponseEntity<BaseResponse<ArticleFiltersResponse>> filters(@RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, articleNewsService.getFilters(QueryTime.resolve(asOf)));
    }

    @GetMapping
    public ResponseEntity<BaseResponse<ArticlePageResponse>> articles(
            @RequestParam(required = false) @Pattern(regexp = "[a-zA-Z]{2}") String countryCode,
            @RequestParam(required = false) @Positive Long fieldId,
            @RequestParam(required = false) @Positive Long themeId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to,
            @RequestParam(defaultValue = "1") @Min(1) int page,
            @RequestParam(defaultValue = "12") @Min(1) @Max(100) int size,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS,
                articleNewsService.getArticles(countryCode, fieldId, themeId, from, to, page, size, QueryTime.resolve(asOf)));
    }

    @GetMapping("/{articleId}")
    public ResponseEntity<BaseResponse<ArticleDetailResponse>> article(@PathVariable String articleId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime asOf) {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, articleNewsService.getArticle(articleId, QueryTime.resolve(asOf)));
    }
}
