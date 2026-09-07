package com.ssafy.witw.domain.theme.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dao.ArticleRepository.RepresentArticleProjection;
import com.ssafy.witw.domain.article.dto.ArticleTone;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.service.CountryFinder;
import com.ssafy.witw.domain.country.entity.Country;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository.PopularThemeTrendRow;
import com.ssafy.witw.domain.theme.dto.PopularThemeTrend;
import com.ssafy.witw.domain.theme.dto.PopularThemeTrend.ThemeTimeStamp;
import com.ssafy.witw.domain.theme.dto.PopularThemeTrend.TimeStamp;
import com.ssafy.witw.domain.theme.dto.PopularThemeResponse;
import com.ssafy.witw.domain.theme.dto.ThemeOverviewResponse;
import com.ssafy.witw.domain.theme.entity.Theme;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.List;

import static java.util.stream.Collectors.groupingBy;
import static java.util.stream.Collectors.toList;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ThemeService {

    private static final int INTERVAL_MINUTES = 60;
    private static final int MAX_LIMIT = 10;

    private final ThemeRepository themeRepository;
    private final CountryFinder countryFinder;
    private final IssueRepository issueRepository;
    private final ArticleRepository articleRepository;

    public ThemeOverviewResponse getThemeOverview(Long themeId, int issueLimit, int articleLimit) {
        validateLimit(issueLimit);
        validateLimit(articleLimit);

        Theme theme = themeRepository.findById(themeId)
                .orElseThrow(() -> new GlobalException(ErrorCode.THEME_NOT_FOUND));

        List<ThemeOverviewResponse.PrimaryIssue> primaryIssues = issueRepository
                .getPrimaryIssuesByThemeId(themeId, issueLimit)
                .stream()
                .map(issue -> new ThemeOverviewResponse.PrimaryIssue(
                        issue.getIssueId(), issue.getIssueTitle()))
                .toList();

        List<RepresentArticle> representArticles = articleRepository
                .getRepresentArticlesByThemeId(themeId, articleLimit)
                .stream()
                .map(RepresentArticle::from)
                .toList();

        return new ThemeOverviewResponse(
                theme.getId(),
                theme.getName(),
                theme.getDescription(),
                primaryIssues,
                representArticles
        );
    }

    private void validateLimit(int limit) {
        if (limit < 1 || limit > MAX_LIMIT) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
    }

    public PopularThemeResponse getPopularThemes(String countryCode, int limit) {

        // TODO: Controller @Valid로 처리 예정
        validateLimit(limit);

        Country country = countryFinder.getCountry(countryCode);

        List<PopularThemeTrend> popularThemes = themeRepository.findPopularThemesWithHourlyTrend(countryCode, limit)
                .stream()
                .collect(groupingBy(PopularThemeTrendRow::getThemeId, LinkedHashMap::new, toList()))
                .values()
                .stream()
                .map(this::toPopularThemeTrend)
                .toList();

        return new PopularThemeResponse(countryCode, country.getNameKo(), popularThemes);
    }

    private PopularThemeTrend toPopularThemeTrend(List<PopularThemeTrendRow> rows) {
        PopularThemeTrendRow theme = rows.getFirst();
        List<TimeStamp> timestamps = rows.stream()
                .map(row -> new TimeStamp(row.getBucketStart(), row.getArticleCount()))
                .toList();

        return new PopularThemeTrend(
                theme.getThemeId(),
                theme.getFieldName(),
                theme.getThemeName(),
                theme.getArticleCount24(),
                new ThemeTimeStamp(INTERVAL_MINUTES, timestamps)
        );
    }
}
