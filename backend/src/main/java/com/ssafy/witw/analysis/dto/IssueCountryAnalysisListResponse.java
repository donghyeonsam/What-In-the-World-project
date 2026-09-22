package com.ssafy.witw.analysis.dto;

import java.time.OffsetDateTime;
import java.util.List;

public record IssueCountryAnalysisListResponse(
        long issueId,
        List<CountryAnalysis> countryAnalyses
) {
    public record CountryAnalysis(
            long analysisId,
            String countryCode,
            String title,
            String summary,
            long articleCount,
            OffsetDateTime windowEnd
    ) { }
}
