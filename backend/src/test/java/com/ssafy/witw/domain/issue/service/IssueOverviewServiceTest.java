package com.ssafy.witw.domain.issue.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dao.ArticleRepository.RepresentArticleProjection;
import com.ssafy.witw.domain.article.dto.ArticleTone;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.dto.CountryPoint;
import com.ssafy.witw.domain.country.dto.CountryTone;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.dto.IssueOverviewResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class IssueOverviewServiceTest {
    @Mock private IssueRepository issueRepository;
    @Mock private ArticleRepository articleRepository;
    @InjectMocks private IssueService issueService;

    @ParameterizedTest
    @CsvSource({"33, NEGATIVE", "33.1, NEUTRAL", "66, NEUTRAL", "66.1, POSITIVE", "67, POSITIVE"})
    void 이슈_프리뷰와_국가_톤과_감정이_변환된_대표_기사를_조립한다(String score, ArticleTone expectedTone) {
        // given
        when(issueRepository.existsById(1L)).thenReturn(true);
        var preview = 프리뷰(8L);
        when(issueRepository.getIssuePreviewByIssueId(1L)).thenReturn(preview);
        var country = mock(IssueRepository.CountryToneRow.class);
        when(country.getCountryCode()).thenReturn("KR");
        when(country.getCountryName()).thenReturn("대한민국");
        when(country.getLongitude()).thenReturn(127.0);
        when(country.getLatitude()).thenReturn(37.5);
        when(country.getToneAvg()).thenReturn(50.0);
        when(country.getToneMin()).thenReturn(20.0);
        when(country.getToneMax()).thenReturn(80.0);
        when(issueRepository.findCountryTonesLast24Hours(1L)).thenReturn(List.of(country));

        var article = mock(RepresentArticleProjection.class);
        LocalDateTime publishedAt = LocalDateTime.of(2026, 9, 7, 12, 0);
        when(article.getArticleId()).thenReturn("article-1");
        when(article.getArticleTitle()).thenReturn("대표 기사 제목");
        when(article.getArticlePublisher()).thenReturn("언론사");
        when(article.getArticleToneScore()).thenReturn(new BigDecimal(score));
        when(article.getPublishedAt()).thenReturn(publishedAt);
        when(articleRepository.getRepresentArticlesByIssueId(1L, 2)).thenReturn(List.of(article));

        // when
        var response = issueService.getIssueOverview(1L, 2);

        // then
        assertThat(response.issuePreview())
                .as("이슈 제목, 테마 제목, 전체 기사 수가 응답에 매핑됨")
                .isEqualTo(new IssueOverviewResponse.IssuePreview("폭염", "기후", 8L));
        assertThat(response.countryTones())
                .as("국가 코드와 이름, 경도와 위도, 평균과 최대·최소가 뒤바뀌지 않음")
                .containsExactly(new CountryTone(new CountryPoint("KR", "대한민국", 127.0, 37.5), 50, 80, 20));
        assertThat(response.representArticles())
                .as("대표 기사 모든 필드를 보존하고 점수 경계에 맞는 ArticleTone으로 변환함")
                .containsExactly(new RepresentArticle("article-1", "대표 기사 제목", expectedTone, "언론사", publishedAt));
        verify(articleRepository).getRepresentArticlesByIssueId(1L, 2);
    }

    @Test
    void 기사가_없는_이슈는_프리뷰와_빈_목록을_반환한다() {
        // given
        when(issueRepository.existsById(1L)).thenReturn(true);
        var preview = 프리뷰(0L);
        when(issueRepository.getIssuePreviewByIssueId(1L)).thenReturn(preview);
        when(issueRepository.findCountryTonesLast24Hours(1L)).thenReturn(List.of());
        when(articleRepository.getRepresentArticlesByIssueId(1L, 3)).thenReturn(List.of());

        // when
        var response = issueService.getIssueOverview(1L, 3);

        // then
        assertThat(response.issuePreview().articleCount()).as("기사 없는 이슈의 기사 수").isZero();
        assertThat(response.countryTones()).as("집계할 기사가 없는 국가 톤 목록").isEmpty();
        assertThat(response.representArticles()).as("대표 기사가 없는 경우 빈 목록 반환").isEmpty();
    }

    @Test
    void 없는_이슈는_예외를_던지고_추가_조회하지_않는다() {
        // given
        when(issueRepository.existsById(99L)).thenReturn(false);

        // when / then
        assertThatThrownBy(() -> issueService.getIssueOverview(99L, 3))
                .as("존재하지 않는 이슈는 ENTITY_NOT_FOUND 반환")
                .isInstanceOfSatisfying(GlobalException.class,
                        exception -> assertThat(exception.getErrorCode()).as("이슈 없음 오류 코드")
                                .isEqualTo(ErrorCode.ENTITY_NOT_FOUND));
        verify(issueRepository).existsById(99L);
        verifyNoMoreInteractions(issueRepository);
        verifyNoInteractions(articleRepository);
    }

    private IssueRepository.IssuePreview 프리뷰(long count) {
        var preview = mock(IssueRepository.IssuePreview.class);
        when(preview.getIssueTitle()).thenReturn("폭염");
        when(preview.getThemeTitle()).thenReturn("기후");
        when(preview.getArticleCount()).thenReturn(count);
        return preview;
    }
}
