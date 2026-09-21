package com.ssafy.witw.domain.theme.service;

import com.ssafy.witw.domain.article.dao.ArticleRepository.RepresentArticleProjection;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dto.ArticleTone;
import com.ssafy.witw.domain.country.service.CountryFinder;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dto.ThemeOverviewResponse;
import com.ssafy.witw.domain.theme.entity.Theme;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ThemeOverviewServiceTest {

    private static final long THEME_ID = 1L;

    @Mock
    private ThemeRepository themeRepository;
    @Mock
    private CountryFinder countryFinder;
    @Mock
    private IssueRepository issueRepository;
    @Mock
    private ArticleRepository articleRepository;

    @Test
    @DisplayName("[테마 개요 조회] 테마와 주요 이슈, 대표 기사를 하나의 응답으로 조립한다")
    void 테마와_주요_이슈_대표_기사를_하나의_응답으로_조립한다() {
        // given
        Theme theme = new Theme();
        theme.setId(THEME_ID);
        theme.setName("기후 변화");
        theme.setDescription("기후 관련 뉴스");

        IssueRepository.PrimaryIssue issue = org.mockito.Mockito.mock(IssueRepository.PrimaryIssue.class);
        when(issue.getIssueId()).thenReturn(10L);
        when(issue.getIssueTitle()).thenReturn("폭염");

        RepresentArticleProjection article = org.mockito.Mockito.mock(RepresentArticleProjection.class);
        when(article.getArticleId()).thenReturn("article-1");
        when(article.getArticleTitle()).thenReturn("폭염이 이어진다");
        when(article.getArticleToneScore()).thenReturn(BigDecimal.valueOf(33));
        when(article.getArticlePublisher()).thenReturn("publisher");
        when(article.getUrl()).thenReturn("https://example.com/article-1");
        when(article.getPublishedAt()).thenReturn(LocalDateTime.of(2026, 1, 1, 12, 0));

        when(themeRepository.findById(THEME_ID)).thenReturn(Optional.of(theme));
        when(issueRepository.getPrimaryIssuesByThemeId(eq(THEME_ID), eq(3), any(LocalDateTime.class), isNull())).thenReturn(List.of(issue));
        when(articleRepository.getRepresentArticlesByThemeId(eq(THEME_ID), eq(10), any(LocalDateTime.class))).thenReturn(List.of(article));

        // when
        ThemeOverviewResponse response = service().getThemeOverview(THEME_ID, 3, 10);

        // then
        assertThat(response.themeId())
                .as("조회한 테마의 ID")
                .isEqualTo(THEME_ID);
        assertThat(response.themeName())
                .as("조회한 테마의 이름")
                .isEqualTo("기후 변화");
        assertThat(response.primaryIssues()).singleElement()
                .as("테마의 주요 이슈 목록")
                .extracting(ThemeOverviewResponse.PrimaryIssue::issueTitle)
                .isEqualTo("폭염");
        assertThat(response.representArticles()).singleElement()
                .as("테마의 대표 기사 목록")
                .extracting(articleResponse -> articleResponse.articleTone())
                .isEqualTo(ArticleTone.NEGATIVE);
    }

    @Test
    @DisplayName("[테마 개요 조회] 국가 코드가 있으면 주요 이슈와 대표 기사를 해당 국가로 조회한다")
    void 국가별_대표_기사를_조회한다() {
        Theme theme = new Theme();
        theme.setId(THEME_ID);
        theme.setName("기후 변화");
        when(themeRepository.findById(THEME_ID)).thenReturn(Optional.of(theme));
        when(issueRepository.getPrimaryIssuesByThemeId(eq(THEME_ID), eq(3), any(LocalDateTime.class), eq("KR"))).thenReturn(List.of());
        when(articleRepository.getRepresentArticlesByThemeIdAndCountryCode(eq(THEME_ID), eq("KR"), eq(10), any(LocalDateTime.class)))
                .thenReturn(List.of());

        service().getThemeOverview(THEME_ID, 3, 10, "KR");

        verify(issueRepository).getPrimaryIssuesByThemeId(eq(THEME_ID), eq(3), any(LocalDateTime.class), eq("KR"));
        verify(articleRepository).getRepresentArticlesByThemeIdAndCountryCode(eq(THEME_ID), eq("KR"), eq(10), any(LocalDateTime.class));
    }

    private ThemeService service() {
        return new ThemeService(themeRepository, countryFinder, issueRepository, articleRepository);
    }
}
