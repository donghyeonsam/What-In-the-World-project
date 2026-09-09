package com.ssafy.witw.domain.theme.service;

import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.country.service.CountryFinder;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository.FieldThemeRow;
import com.ssafy.witw.domain.theme.dto.FieldThemesResponse;
import com.ssafy.witw.domain.theme.dto.FieldThemesResponse.ThemeCount;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class FieldThemesServiceTest {

    @Mock
    private ThemeRepository themeRepository;
    @Mock
    private CountryFinder countryFinder;
    @Mock
    private IssueRepository issueRepository;
    @Mock
    private ArticleRepository articleRepository;

    @Test
    @DisplayName("[분야별 테마 조회] 분야별로 테마를 묶고 기사 0건인 테마와 테마가 없는 분야도 반환한다")
    void 분야별로_테마를_묶고_기사_없는_테마와_빈_분야도_반환한다() {
        // given
        when(themeRepository.findThemesByField()).thenReturn(List.of(
                row(1L, 10L, 3), row(1L, 11L, 0), row(2L, null, 0)));

        // when
        List<FieldThemesResponse> response = service().getThemesByField();

        // then
        assertThat(response)
                .as("행을 분야 단위로 접어서 반환한다")
                .extracting(FieldThemesResponse::fieldId, FieldThemesResponse::fieldName)
                .containsExactly(tuple(1L, "Field 1"), tuple(2L, "Field 2"));
        assertThat(response.getFirst().themes())
                .as("기사가 0건인 테마도 목록에 남긴다")
                .extracting(ThemeCount::themeId, ThemeCount::themeName, ThemeCount::articleCount24)
                .containsExactly(tuple(10L, "Theme 10", 3L), tuple(11L, "Theme 11", 0L));
        assertThat(response.get(1).themes())
                .as("LEFT JOIN 으로 생긴 themeId null 행은 테마로 세지 않는다")
                .isEmpty();
    }

    @Test
    @DisplayName("[분야별 테마 조회] 등록된 분야가 없으면 빈 목록을 반환한다")
    void 등록된_분야가_없으면_빈_목록을_반환한다() {
        // given
        when(themeRepository.findThemesByField()).thenReturn(List.of());

        // when
        List<FieldThemesResponse> response = service().getThemesByField();

        // then
        assertThat(response).as("집계할 분야가 없는 경우").isEmpty();
    }

    private ThemeService service() {
        return new ThemeService(themeRepository, countryFinder, issueRepository, articleRepository);
    }

    private FieldThemeRow row(Long fieldId, Long themeId, long count) {
        return new FieldThemeRow() {
            public Long getFieldId() { return fieldId; }
            public String getFieldName() { return "Field " + fieldId; }
            public Long getThemeId() { return themeId; }
            public String getThemeName() { return themeId == null ? null : "Theme " + themeId; }
            public long getArticleCount24() { return count; }
        };
    }
}
