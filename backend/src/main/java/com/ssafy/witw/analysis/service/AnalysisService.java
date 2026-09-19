package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.dto.IssueCountryAnalysisDetailResponse;
import com.ssafy.witw.analysis.dto.IssueCountryAnalysisListResponse;

import java.time.LocalDateTime;

public interface AnalysisService {
    IssueCountryAnalysisListResponse getCountryAnalyses(long issueId, LocalDateTime asOf);

    IssueCountryAnalysisDetailResponse getCountryAnalysis(long issueId, String countryCode, LocalDateTime asOf);
}
