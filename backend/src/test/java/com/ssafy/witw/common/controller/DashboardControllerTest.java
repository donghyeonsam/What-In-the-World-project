package com.ssafy.witw.common.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dto.ArticleTone;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.controller.CountryController;
import com.ssafy.witw.domain.country.dto.CountryMainResponse;
import com.ssafy.witw.domain.country.dto.CountryPoint;
import com.ssafy.witw.domain.country.dto.CountryTone;
import com.ssafy.witw.domain.country.service.CountryService;
import com.ssafy.witw.domain.issue.controller.GlobalIssueController;
import com.ssafy.witw.domain.issue.controller.IssueController;
import com.ssafy.witw.domain.issue.dto.GlobalIssueDetailResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse;
import com.ssafy.witw.domain.issue.dto.IssueInfo;
import com.ssafy.witw.domain.issue.dto.IssueOverviewResponse;
import com.ssafy.witw.domain.issue.service.IssueService;
import com.ssafy.witw.domain.theme.controller.ThemeController;
import com.ssafy.witw.domain.theme.dto.FieldThemesResponse;
import com.ssafy.witw.domain.theme.dto.PopularTheme;
import com.ssafy.witw.domain.theme.dto.PopularThemeResponse;
import com.ssafy.witw.domain.theme.dto.PopularThemeTrend;
import com.ssafy.witw.domain.theme.dto.ThemeOverviewResponse;
import com.ssafy.witw.domain.theme.service.ThemeService;
import com.ssafy.witw.common.security.config.SecurityConfig;
import com.ssafy.witw.infra.OpenApiConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springdoc.core.configuration.SpringDocConfiguration;
import org.springdoc.core.properties.SpringDocConfigProperties;
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springdoc.core.properties.SwaggerUiOAuthProperties;
import org.springdoc.webmvc.core.configuration.SpringDocWebMvcConfiguration;
import org.springdoc.webmvc.ui.SwaggerConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.List;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = {ThemeController.class, CountryController.class,
        GlobalIssueController.class, IssueController.class}, properties = {
        "app.cors.allowed-origins=http://localhost:5173",
        "app.cors.allowed-methods=GET,OPTIONS",
        "app.cors.allowed-headers=*"
})
@Import({SecurityConfig.class, OpenApiConfig.class})
@ImportAutoConfiguration({SpringDocConfiguration.class, SpringDocConfigProperties.class,
        SpringDocWebMvcConfiguration.class, SwaggerConfig.class,
        SwaggerUiConfigProperties.class, SwaggerUiOAuthProperties.class})
class DashboardControllerTest {
    private static final LocalDateTime TIME = LocalDateTime.of(2026, 9, 8, 12, 0);
    @Autowired private MockMvc mvc;
    @MockitoBean private ThemeService themeService;
    @MockitoBean private CountryService countryService;
    @MockitoBean private IssueService issueService;

    @Test
    @DisplayName("[글로벌 대시보드] 로그인 없이 기사 수와 이슈 순위를 공통 응답으로 조회한다")
    void 로그인_없이_글로벌_기사_수와_이슈_순위를_조회한다() throws Exception {
        // given
        when(issueService.getGlobalIssueRank()).thenReturn(new GlobalIssueRankResponse(100, 20,
                List.of(new GlobalIssueRankResponse.GlobalIssue(1, "환경", "기후", "폭염", 10, TIME))));

        // when / then
        mvc.perform(get("/api/v1/global/issues"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").isNotEmpty())
                .andExpect(jsonPath("$.code").doesNotExist())
                .andExpect(jsonPath("$.data.totalArticleCount").value(100))
                .andExpect(jsonPath("$.data.recent24ArticleCount").value(20))
                .andExpect(jsonPath("$.data.globalIssues[0].issueId").value(1))
                .andExpect(jsonPath("$.data.globalIssues[0].firstSeenAt").value("2026-09-08T12:00:00"));
        verify(issueService).getGlobalIssueRank();
    }

    @Test
    @DisplayName("[글로벌 이슈 상세] 로그인 없이 이슈 정보와 좌표를 포함한 국가별 논조를 조회한다")
    void 로그인_없이_이슈_상세와_국가별_논조를_조회한다() throws Exception {
        // given
        when(issueService.getGlobalIssueDetail(1)).thenReturn(new GlobalIssueDetailResponse(
                new IssueInfo(1, "폭염", 10, 1), List.of(countryTone())));

        // when / then
        mvc.perform(get("/api/v1/global/issues/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.issueInfo.issueName").value("폭염"))
                .andExpect(jsonPath("$.data.countryTones[0].country.countryCode").value("KR"))
                .andExpect(jsonPath("$.data.countryTones[0].country.lng").value(127.0))
                .andExpect(jsonPath("$.data.countryTones[0].country.lat").value(37.5))
                .andExpect(jsonPath("$.data.countryTones[0].toneAvg").value(50.0))
                .andExpect(jsonPath("$.data.countryTones[0].toneSd").value(12.5))
                .andExpect(jsonPath("$.data.countryTones[0].articleCount").value(4));
        verify(issueService).getGlobalIssueDetail(1);
    }

    @Test
    @DisplayName("[이슈 미리보기] 로그인 없이 기본 대표 기사 3개를 요청하고 기사 날짜와 논조를 반환한다")
    void 로그인_없이_이슈_미리보기의_기본_대표_기사를_조회한다() throws Exception {
        // given
        when(issueService.getIssueOverview(1, 3, null)).thenReturn(new IssueOverviewResponse(
                new IssueOverviewResponse.IssuePreview("폭염", "기후", 10),
                List.of(countryTone()), List.of(article())));

        // when / then
        mvc.perform(get("/api/v1/issues/1/overview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.issuePreview.issueTitle").value("폭염"))
                .andExpect(jsonPath("$.data.representArticles[0].articleTone").value("NEUTRAL"))
                .andExpect(jsonPath("$.data.representArticles[0].publishedAt").value("2026-09-08T12:00:00"));
        verify(issueService).getIssueOverview(1, 3, null);
    }

    @Test
    @DisplayName("[국가 대시보드] 로그인 없이 소문자 국가 코드를 대문자로 변환하여 조회한다")
    void 로그인_없이_소문자_국가_코드로_대시보드를_조회한다() throws Exception {
        // given
        when(countryService.getCountryMain("KR")).thenReturn(new CountryMainResponse("KR", "대한민국", 12, 2,
                List.of(new PopularTheme(1, "환경", "기후", 5)),
                List.of(new CountryMainResponse.MentionRatio("US", "미국", 0.5)),
                List.of(), List.of(article())));

        // when / then
        mvc.perform(get("/api/v1/countries/kr"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.countryCode").value("KR"))
                .andExpect(jsonPath("$.data.todayArticleCount").value(12))
                .andExpect(jsonPath("$.data.globalRank").value(2))
                .andExpect(jsonPath("$.data.popularThemes[0].themeId").value(1))
                .andExpect(jsonPath("$.data.sourceMentions[0].mentionRatio").value(0.5))
                .andExpect(jsonPath("$.data.targetMentions").isEmpty());
        verify(countryService).getCountryMain("KR");
    }

    @Test
    @DisplayName("[국가별 인기 테마] 로그인 없이 기본 3개 테마와 시간별 기사 수를 조회한다")
    void 로그인_없이_인기_테마와_시간별_기사_수를_조회한다() throws Exception {
        // given
        when(themeService.getPopularThemes("KR", 3)).thenReturn(new PopularThemeResponse("KR", "대한민국",
                List.of(new PopularThemeTrend(1, "환경", "기후", 5,
                        new PopularThemeTrend.ThemeTimeStamp(60,
                                List.of(new PopularThemeTrend.TimeStamp(TIME, 5)))))));

        // when / then
        mvc.perform(get("/api/v1/countries/kr/themes/popular"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.popularThemes[0].articleCount24").value(5))
                .andExpect(jsonPath("$.data.popularThemes[0].themeTimeStamp.interval").value(60))
                .andExpect(jsonPath("$.data.popularThemes[0].themeTimeStamp.timestamp[0].time")
                        .value("2026-09-08T12:00:00"));
        verify(themeService).getPopularThemes("KR", 3);
    }

    @Test
    @DisplayName("[테마 개요] 로그인 없이 기본 주요 이슈 3개와 대표 기사 10개를 요청한다")
    void 로그인_없이_테마_개요를_기본_조회_개수로_조회한다() throws Exception {
        // given
        when(themeService.getThemeOverview(1L, 3, 10, null)).thenReturn(new ThemeOverviewResponse(1L, "기후", "기후 뉴스",
                List.of(new ThemeOverviewResponse.PrimaryIssue(1L, "폭염")), List.of(article())));

        // when / then
        mvc.perform(get("/api/v1/themes/1/overview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.themeName").value("기후"))
                .andExpect(jsonPath("$.data.primaryIssues[0].issueId").value(1))
                .andExpect(jsonPath("$.data.representArticles[0].articleId").value("article-1"));
        verify(themeService).getThemeOverview(1L, 3, 10, null);
    }

    @Test
    @DisplayName("[분야별 테마] 로그인 없이 기사 없는 테마도 0건으로 반환한다")
    void 로그인_없이_분야별_테마를_조회한다() throws Exception {
        // given
        when(themeService.getThemesByField()).thenReturn(List.of(new FieldThemesResponse(1L, "환경",
                List.of(new FieldThemesResponse.ThemeCount(1L, "기후", 0)))));

        // when / then
        mvc.perform(get("/api/v1/themes/by-field"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].fieldId").value(1))
                .andExpect(jsonPath("$.data[0].themes[0].articleCount24").value(0));
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 10})
    @DisplayName("[조회 개수] 최소·최대 조회 개수를 서비스에 그대로 전달한다")
    void 최소_최대_조회_개수를_서비스에_전달한다(int limit) throws Exception {
        // given
        when(themeService.getPopularThemes("KR", limit)).thenReturn(new PopularThemeResponse("KR", "대한민국", List.of()));
        when(themeService.getThemeOverview(1L, limit, limit, null)).thenReturn(new ThemeOverviewResponse(1L, "기후", "설명", List.of(), List.of()));
        when(issueService.getIssueOverview(1, limit, null)).thenReturn(new IssueOverviewResponse(
                new IssueOverviewResponse.IssuePreview("폭염", "기후", 0), List.of(), List.of()));

        // when / then
        mvc.perform(get("/api/v1/countries/KR/themes/popular").param("limit", String.valueOf(limit))).andExpect(status().isOk());
        mvc.perform(get("/api/v1/themes/1/overview").param("issueLimit", String.valueOf(limit))
                .param("articleLimit", String.valueOf(limit))).andExpect(status().isOk());
        mvc.perform(get("/api/v1/issues/1/overview").param("articleLimit", String.valueOf(limit))).andExpect(status().isOk());
        verify(themeService).getPopularThemes("KR", limit);
        verify(themeService).getThemeOverview(1L, limit, limit, null);
        verify(issueService).getIssueOverview(1, limit, null);
    }

    @ParameterizedTest
    @CsvSource({
            "/api/v1/global/issues/0, CO01", "/api/v1/global/issues/abc, CO06",
            "/api/v1/global/issues/9223372036854775808, CO06",
            "/api/v1/issues/-1/overview, CO01", "/api/v1/issues/abc/overview, CO06",
            "/api/v1/themes/0/overview, CO01", "/api/v1/themes/abc/overview, CO06",
            "/api/v1/countries/K, CO01", "/api/v1/countries/KOR/themes/popular, CO01",
            "/api/v1/countries/12, CO01", "/api/v1/countries/KR/themes/popular?limit=0, CO01",
            "/api/v1/countries/KR/themes/popular?limit=11, CO01",
            "/api/v1/countries/KR/themes/popular?limit=abc, CO06",
            "/api/v1/themes/1/overview?issueLimit=0, CO01",
            "/api/v1/themes/1/overview?issueLimit=11, CO01",
            "/api/v1/themes/1/overview?articleLimit=0, CO01",
            "/api/v1/themes/1/overview?articleLimit=11, CO01",
            "/api/v1/issues/1/overview?articleLimit=0, CO01",
            "/api/v1/issues/1/overview?articleLimit=11, CO01",
            "/api/v1/issues/1/overview?articleLimit=abc, CO06"
    })
    @DisplayName("[요청 검증] 잘못된 ID·국가 코드·조회 개수는 서비스 호출 없이 400으로 응답한다")
    void 잘못된_요청은_서비스_호출_전에_거부한다(String path, String code) throws Exception {
        // when / then
        mvc.perform(get(path))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code").value(code))
                .andExpect(jsonPath("$.message").isNotEmpty())
                .andExpect(jsonPath("$.data").doesNotExist());
        verifyNoInteractions(themeService, countryService, issueService);
    }

    @ParameterizedTest
    @CsvSource({"/api/v1/global/issues/99, CO03", "/api/v1/issues/99/overview, CO03",
            "/api/v1/themes/99/overview, TH01", "/api/v1/countries/ZZ, CT01",
            "/api/v1/countries/ZZ/themes/popular, CT01"})
    @DisplayName("[미존재 데이터] 없는 이슈·테마·국가는 서비스 오류 코드를 유지하여 404로 응답한다")
    void 존재하지_않는_조회_대상은_404로_응답한다(String path, String code) throws Exception {
        // given
        when(issueService.getGlobalIssueDetail(99)).thenThrow(new GlobalException(ErrorCode.ENTITY_NOT_FOUND));
        when(issueService.getIssueOverview(99, 3, null)).thenThrow(new GlobalException(ErrorCode.ENTITY_NOT_FOUND));
        when(themeService.getThemeOverview(99L, 3, 10, null)).thenThrow(new GlobalException(ErrorCode.THEME_NOT_FOUND));
        when(countryService.getCountryMain("ZZ")).thenThrow(new GlobalException(ErrorCode.COUNTRY_NOT_FOUND));
        when(themeService.getPopularThemes("ZZ", 3)).thenThrow(new GlobalException(ErrorCode.COUNTRY_NOT_FOUND));

        // when / then
        mvc.perform(get(path)).andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404)).andExpect(jsonPath("$.code").value(code));
    }

    @Test
    @DisplayName("[서버 오류] 내부 예외 내용은 노출하지 않고 공통 500 응답을 반환한다")
    void 예상하지_못한_오류는_공통_500으로_응답한다() throws Exception {
        // given
        when(issueService.getGlobalIssueRank()).thenThrow(new IllegalStateException("internal database detail"));

        // when / then
        mvc.perform(get("/api/v1/global/issues"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value(500))
                .andExpect(jsonPath("$.code").value("CO99"))
                .andExpect(jsonPath("$.message").value(ErrorCode.INTERNAL_SERVER_ERROR.getMessage()));
    }

    @ParameterizedTest
    @ValueSource(strings = {"/api/themes/by-field", "/api/v1/not-found"})
    @DisplayName("[요청 경로] 이전 버전 경로와 없는 경로는 공통 404 응답을 반환한다")
    void 이전_경로와_없는_경로는_404로_응답한다(String path) throws Exception {
        // when / then
        mvc.perform(get(path)).andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("CO13"));
    }

    @Test
    @DisplayName("[HTTP 메서드] 조회 API의 POST 요청은 허용 메서드와 함께 405로 응답한다")
    void 지원하지_않는_메서드는_405로_응답한다() throws Exception {
        // when / then
        mvc.perform(post("/api/v1/global/issues"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string("Allow", containsString("GET")))
                .andExpect(jsonPath("$.code").value("CO04"));
    }

    @Test
    @DisplayName("[CORS] 허용한 프론트엔드의 사전 요청은 로그인 없이 처리한다")
    void 허용한_출처의_사전_요청을_처리한다() throws Exception {
        // when / then
        mvc.perform(options("/api/v1/themes/by-field")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "GET")
                        .header("Access-Control-Request-Headers", "Content-Type"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:5173"));
        verifyNoInteractions(themeService, countryService, issueService);
    }

    @Test
    @DisplayName("[CORS] 설정하지 않은 출처의 요청은 거부한다")
    void 허용하지_않은_출처의_요청은_거부한다() throws Exception {
        // when / then
        mvc.perform(get("/api/v1/themes/by-field").header("Origin", "https://unconfigured.example"))
                .andExpect(status().isForbidden());
        verifyNoInteractions(themeService, countryService, issueService);
    }

    @Test
    @DisplayName("[Swagger] 로그인 없이 7개 API의 파라미터·성공·오류 스키마와 UI를 조회한다")
    void 로그인_없이_스웨거_문서와_UI에_접근한다() throws Exception {
        // when / then
        mvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.info.title").value("WITW 조회 API"))
                .andExpect(jsonPath("$.paths.*", hasSize(7)))
                .andExpect(jsonPath("$.paths['/api/v1/themes/{themeId}/overview'].get.parameters", hasSize(4)))
                .andExpect(jsonPath("$.paths['/api/v1/global/issues'].get.responses['200'].content['application/json'].schema").exists())
                .andExpect(jsonPath("$.paths['/api/v1/global/issues'].get.responses['400'].content['application/json'].schema['$ref']")
                        .value("#/components/schemas/ApiError"));
        mvc.perform(get("/swagger-ui.html"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/swagger-ui/index.html"));
        mvc.perform(get("/swagger-ui/index.html")).andExpect(status().isOk());
        mvc.perform(get("/v3/api-docs/swagger-config")).andExpect(status().isOk());
    }

    private CountryTone countryTone() {
        return new CountryTone(new CountryPoint("KR", "대한민국", 127, 37.5), 50, 80, 20, 12.5, 4);
    }

    private RepresentArticle article() {
        return new RepresentArticle("article-1", "폭염 기사", ArticleTone.NEUTRAL, "언론사", TIME);
    }
}
