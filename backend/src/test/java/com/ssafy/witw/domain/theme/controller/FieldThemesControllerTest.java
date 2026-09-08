package com.ssafy.witw.domain.theme.controller;

import com.ssafy.witw.domain.theme.dto.FieldThemesResponse;
import com.ssafy.witw.domain.theme.dto.FieldThemesResponse.ThemeCount;
import com.ssafy.witw.domain.theme.service.ThemeService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// addFilters = false: SecurityConfig 는 @WebMvcTest 슬라이스에 포함되지 않아
// 켜두면 시큐리티 기본 정책이 걸려 401 이 된다.
@WebMvcTest(ThemeController.class)
@ActiveProfiles("test")
@AutoConfigureMockMvc(addFilters = false)
class FieldThemesControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ThemeService themeService;

    @Test
    @DisplayName("[분야별 테마 조회] 200과 공통 성공 응답 및 분야-테마 구조를 반환한다")
    void 성공하면_공통_성공_응답에_분야별_테마를_담아_반환한다() throws Exception {
        // given
        when(themeService.getThemesByField()).thenReturn(List.of(
                new FieldThemesResponse(1L, "Field 1", List.of(
                        new ThemeCount(10L, "Theme 10", 3),
                        new ThemeCount(11L, "Theme 11", 0))),
                new FieldThemesResponse(2L, "Field 2", List.of())));

        // when
        var result = mvc.perform(get("/api/v1/themes/by-field"));

        // then
        result
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("요청이 성공적으로 처리되었습니다."))
                .andExpect(jsonPath("$.code").doesNotExist())
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
    @DisplayName("[분야별 테마 조회] 반환할 분야가 없으면 200과 빈 배열을 반환한다")
    void 반환할_분야가_없으면_빈_배열을_반환한다() throws Exception {
        // given
        when(themeService.getThemesByField()).thenReturn(List.of());

        // when
        var result = mvc.perform(get("/api/v1/themes/by-field"));

        // then
        result
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data").isEmpty());
    }
}
