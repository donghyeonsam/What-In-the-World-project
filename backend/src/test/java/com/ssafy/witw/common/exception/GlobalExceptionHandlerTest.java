package com.ssafy.witw.common.exception;

import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.theme.controller.ThemeController;
import com.ssafy.witw.domain.theme.service.ThemeService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// ThemeController 는 어드바이스를 태우기 위한 통로다.
// addFilters = false: SecurityFilterChain 빈이 없어 켜두면 모든 요청이 401 이 된다.
@WebMvcTest(ThemeController.class)
@ActiveProfiles("test")
@AutoConfigureMockMvc(addFilters = false)
class GlobalExceptionHandlerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ThemeService themeService;

    @ParameterizedTest(name = "{0} -> HTTP {1}, code {2}")
    @CsvSource({
            "THEME_NOT_FOUND,      404, TH01",
            "COUNTRY_NOT_FOUND,    404, CT01",
            "INVALID_INPUT_VALUE,  400, CO01",
            "INTERNAL_SERVER_ERROR, 500, CO99",
    })
    @DisplayName("[예외 처리] GlobalException 은 ErrorCode 의 상태코드와 코드, 메시지로 응답한다")
    void GlobalException은_ErrorCode에_정의된_응답으로_변환된다(
            ErrorCode errorCode, int expectedStatus, String expectedCode) throws Exception {
        // given
        when(themeService.getThemesByField()).thenThrow(new GlobalException(errorCode));

        // when
        var result = mvc.perform(get("/api/themes/by-field"));

        // then
        result
                .andExpect(status().is(expectedStatus))
                .andExpect(jsonPath("$.status").value(expectedStatus))
                .andExpect(jsonPath("$.code").value(expectedCode))
                .andExpect(jsonPath("$.message").value(errorCode.getMessage()))
                .andExpect(jsonPath("$.data").doesNotExist());
    }

    @Test
    @DisplayName("[예외 처리] 처리하지 않은 예외는 내부 메시지를 감추고 500으로 응답한다")
    void 처리하지_않은_예외는_500_공통_오류로_응답한다() throws Exception {
        // given
        when(themeService.getThemesByField())
                .thenThrow(new IllegalStateException("DB 커넥션 풀 고갈 - 노출되면 안 되는 내부 메시지"));

        // when
        var result = mvc.perform(get("/api/themes/by-field"));

        // then
        result
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value(500))
                .andExpect(jsonPath("$.code").value(ErrorCode.INTERNAL_SERVER_ERROR.getCode()))
                .andExpect(jsonPath("$.message")
                        .value(ErrorCode.INTERNAL_SERVER_ERROR.getMessage()))
                .andExpect(jsonPath("$.data").doesNotExist());
    }
}
