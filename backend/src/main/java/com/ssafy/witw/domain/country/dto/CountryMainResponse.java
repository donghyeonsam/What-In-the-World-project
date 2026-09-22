package com.ssafy.witw.domain.country.dto;

import com.ssafy.witw.domain.theme.dto.PopularTheme;

import java.util.List;

public record CountryMainResponse(
        String countryCode,
        String countryName,
        long todayArticleCount,
        int globalRank,

        List<CountryIssue> countryIssues,
        List<PopularTheme> popularThemes,
        List<MentionRatio> sourceMentions,
        List<MentionRatio> targetMentions
) {
    public record CountryIssue(
            long issueId,
            String fieldName,
            String themeName,
            String issueName,
            String scoreVersion,
            Double localHeatScore
    ) { }

    public record MentionRatio(
            String countryCode,
            String countryName,
            double mentionRatio
    ) { }
}
