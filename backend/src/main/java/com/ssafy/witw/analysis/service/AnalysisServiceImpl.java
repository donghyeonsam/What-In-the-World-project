package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.dto.IssueCountryAnalysisDetailResponse;
import com.ssafy.witw.analysis.dto.IssueCountryAnalysisListResponse;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisQueryRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisQueryRepository.AnalysisRow;
import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

@Service
@RequiredArgsConstructor
public class AnalysisServiceImpl implements AnalysisService {
    private static final ZoneId ANALYSIS_ZONE = ZoneId.of("Asia/Seoul");

    private final IssueCountryAnalysisQueryRepository queryRepository;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional(readOnly = true)
    public IssueCountryAnalysisListResponse getCountryAnalyses(long issueId, LocalDateTime asOf) {
        requireIssue(issueId, asOf);
        var countryAnalyses = queryRepository.findLatestByIssue(issueId, asOf).stream()
                .map(row -> new IssueCountryAnalysisListResponse.CountryAnalysis(
                        row.id(), row.countryCode(), row.title(), row.summary(),
                        row.articleCount(), row.createdAt().atZone(ANALYSIS_ZONE).toOffsetDateTime()))
                .toList();
        return new IssueCountryAnalysisListResponse(issueId, countryAnalyses);
    }

    @Override
    @Transactional(readOnly = true)
    public IssueCountryAnalysisDetailResponse getCountryAnalysis(long issueId, String countryCode, LocalDateTime asOf) {
        requireIssue(issueId, asOf);
        return new IssueCountryAnalysisDetailResponse(queryRepository.findLatestByIssueAndCountry(issueId, countryCode, asOf)
                .map(this::toDetail)
                .orElse(null));
    }

    private void requireIssue(long issueId, LocalDateTime asOf) {
        if (!queryRepository.issueExistsAt(issueId, asOf)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }
    }

    private IssueCountryAnalysisDetailResponse.Analysis toDetail(AnalysisRow row) {
        return new IssueCountryAnalysisDetailResponse.Analysis(
                row.id(), row.issueId(), row.countryCode(), row.title(), row.summary(),
                parseDetails(row.details()), row.articleCount(),
                row.createdAt().atZone(ANALYSIS_ZONE).toOffsetDateTime());
    }

    private List<String> parseDetails(String detailsJson) {
        try {
            Object parsed = objectMapper.readValue(detailsJson, Object.class);
            if (!(parsed instanceof List<?> details)
                    || details.stream().anyMatch(item -> !(item instanceof String))) {
                throw new IllegalStateException("Stored analysis details must be a JSON string array");
            }
            return details.stream().map(item -> (String) item).toList();
        } catch (JacksonException exception) {
            throw new IllegalStateException("Stored analysis details are not valid JSON", exception);
        }
    }
}
