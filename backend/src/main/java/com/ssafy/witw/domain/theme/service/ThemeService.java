package com.ssafy.witw.domain.theme.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dao.ArticleRepository.RepresentArticleProjection;
import com.ssafy.witw.domain.article.dto.ArticleTone;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.country.entity.Country;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository.PopularThemeRow;
import com.ssafy.witw.domain.theme.dto.PopularTheme;
import com.ssafy.witw.domain.theme.dto.PopularTheme.ThemeTimeStamp;
import com.ssafy.witw.domain.theme.dto.PopularTheme.TimeStamp;
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
    private final CountryRepository countryRepository;
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
                .map(this::toRepresentArticle)
                .toList();

        return new ThemeOverviewResponse(
                theme.getId(),
                theme.getName(),
                theme.getDescription(),
                primaryIssues,
                representArticles
        );
    }

    private RepresentArticle toRepresentArticle(RepresentArticleProjection article) {
        return new RepresentArticle(
                article.getArticleId(),
                article.getArticleTitle(),
                ArticleTone.fromScore(article.getArticleToneScore()),
                article.getArticlePublisher(),
                article.getPublishedAt()
        );
    }

    private void validateLimit(int limit) {
        if (limit < 1 || limit > MAX_LIMIT) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
    }

    public PopularThemeResponse getPopularThemes(String countryCode, int limit) {

        // TODO: Controller @Valid로 처리 예정
        if (limit < 1 || limit > MAX_LIMIT) {
            throw new IllegalArgumentException("limit은 1 이상 10 이하여야 합니다.");
        }

        // TODO: 공통 예외처리 로직으로 처리 예정
        Country country = countryRepository.findById(countryCode)
                .orElseThrow(() -> new IllegalArgumentException("존재하지 않는 국가입니다."));

        List<PopularTheme> popularThemes = themeRepository.findPopularThemes(countryCode, limit)
                .stream()
                .collect(groupingBy(PopularThemeRow::getThemeId, LinkedHashMap::new, toList()))
                .values()
                .stream()
                .map(this::toPopularTheme)
                .toList();

        return new PopularThemeResponse(countryCode, country.getNameKo(), popularThemes);
    }

    private PopularTheme toPopularTheme(List<PopularThemeRow> rows) {
        PopularThemeRow theme = rows.getFirst();
        List<TimeStamp> timestamps = rows.stream()
                .map(row -> new TimeStamp(row.getBucketStart(), row.getArticleCount()))
                .toList();

        return new PopularTheme(
                theme.getThemeId(),
                theme.getFieldName(),
                theme.getThemeName(),
                theme.getArticleCount24(),
                new ThemeTimeStamp(INTERVAL_MINUTES, timestamps)
        );
    }
}
