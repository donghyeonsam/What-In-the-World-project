package com.ssafy.witw.domain.theme.controller;

import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository.FieldThemeRow;
import com.ssafy.witw.domain.theme.service.ThemeService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class FieldThemesControllerTest {
    @Test
    @DisplayName("[분야별 테마 조회] 분야별로 테마를 묶고 기사 0건인 테마와 테마가 없는 분야도 반환한다")
    void 분야별로_테마를_묶고_기사_없는_테마와_빈_분야도_반환한다() throws Exception {
        // given
        ThemeRepository repository = mock(ThemeRepository.class);
        when(repository.findThemesByField()).thenReturn(List.of(
                row(1L, 10L, 3), row(1L, 11L, 0), row(2L, null, 0)));
        var mvc = MockMvcBuilders.standaloneSetup(new ThemeController(
                new ThemeService(repository, null, null, null))).build();

        // when
        var result = mvc.perform(get("/api/v1/themes/by-field"));

        // then
        result
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data.length()").value(2))
                .andExpect(jsonPath("$.data[0].fieldId").value(1))
                .andExpect(jsonPath("$.data[0].fieldName").value("Field 1"))
                .andExpect(jsonPath("$.data[0].themes.length()").value(2))
                .andExpect(jsonPath("$.data[0].themes[0].themeId").value(10))
                .andExpect(jsonPath("$.data[0].themes[0].themeName").value("Theme 10"))
                .andExpect(jsonPath("$.data[0].themes[0].articleCount24").value(3))
                .andExpect(jsonPath("$.data[0].themes[1].articleCount24").value(0))
                .andExpect(jsonPath("$.data[1].themes").isEmpty());
    }

    @Test
    @DisplayName("[분야별 테마 조회] 등록된 분야가 없으면 성공 응답과 빈 목록을 반환한다")
    void 등록된_분야가_없으면_빈_목록을_반환한다() throws Exception {
        // given
        ThemeRepository repository = mock(ThemeRepository.class);
        when(repository.findThemesByField()).thenReturn(List.of());
        var mvc = MockMvcBuilders.standaloneSetup(new ThemeController(
                new ThemeService(repository, null, null, null))).build();

        // when
        var result = mvc.perform(get("/api/v1/themes/by-field"));

        // then
        result
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").isEmpty());
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
