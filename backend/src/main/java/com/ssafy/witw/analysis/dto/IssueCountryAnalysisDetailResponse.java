package com.ssafy.witw.analysis.dto;

import java.time.OffsetDateTime;
import java.util.List;

public record IssueCountryAnalysisDetailResponse(Analysis analysis) {
    public record Analysis(
            long analysisId,
            long issueId,
            String countryCode,
            String title,
            String summary,
            List<String> details,
            long articleCount,
            OffsetDateTime windowEnd
    ) { }
}
