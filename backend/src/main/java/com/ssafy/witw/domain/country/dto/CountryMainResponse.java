package com.ssafy.witw.domain.country.dto;

import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.theme.dto.PopularTheme;

import java.util.List;

public record CountryMainResponse(
        String countryCode,
        String countryName,
        long todayArticleCount,
        int globalRank,

        List<PopularTheme> popularThemes,
        List<MentionRatio> sourceMentions,
        List<MentionRatio> targetMentions,
        List<RepresentArticle> representArticles
) {
    public record MentionRatio(
            String countryCode,
            String countryName,
            double mentionRatio
    ) { }
}
