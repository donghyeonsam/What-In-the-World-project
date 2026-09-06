package com.ssafy.witw.domain.theme.service;

import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dto.PopularTheme;
import com.ssafy.witw.domain.theme.dto.PopularThemeResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace.NONE;

@DataJpaTest
@AutoConfigureTestDatabase(replace = NONE)
class ThemeServiceTest {

    private static final String COUNTRY_CODE = "ZZ";
    private static final long FIELD_ID = 900_001L;
    private static final long POPULAR_THEME_ID = 900_001L;
    private static final long OTHER_THEME_ID = 900_002L;

    @Autowired
    private ThemeRepository themeRepository;

    @Autowired
    private CountryRepository countryRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void 인기_테마와_24개의_시간대를_반환한다() {
        // given
        prepareData();
        ThemeService themeService = new ThemeService(themeRepository, countryRepository);

        // when
        PopularThemeResponse response = themeService.getPopularThemes(COUNTRY_CODE, 1);

        // then
        assertThat(response.countryName())
                .as("조회한 국가의 한글 이름")
                .isEqualTo("테스트국");
        assertThat(response.popularThemes())
                .as("limit에 맞춰 선정된 인기 테마")
                .hasSize(1);

        PopularTheme theme = response.popularThemes().getFirst();
        assertThat(theme.themeId())
                .as("가장 많은 기사를 가진 테마 ID")
                .isEqualTo(POPULAR_THEME_ID);
        assertThat(theme.articleCount24())
                .as("삭제된 기사를 제외한 24시간 기사 수")
                .isEqualTo(2);
        assertThat(theme.themeTimeStamp().interval())
                .as("시간대 간격(분)")
                .isEqualTo(60);
        assertThat(theme.themeTimeStamp().timestamp())
                .as("최근 24시간의 시간대 버킷")
                .hasSize(24);
        assertThat(theme.themeTimeStamp().timestamp())
                .as("기사가 없는 시간대는 0으로 채운 시간당 기사 수")
                .allMatch(timestamp -> timestamp.articleCount() == 0 || timestamp.articleCount() == 1);
        assertThat(theme.themeTimeStamp().timestamp().stream()
                .mapToLong(PopularTheme.TimeStamp::articleCount)
                .sum())
                .as("시간대별 기사 수의 합계")
                .isEqualTo(theme.articleCount24());
    }

    private void prepareData() {
        jdbcTemplate.update("INSERT INTO country VALUES (?, ?, ?)", COUNTRY_CODE, "테스트국", "Test Country");
        jdbcTemplate.update("INSERT INTO field (id, code, name, description) VALUES (?, ?, ?, ?)",
                FIELD_ID, "TEST", "테스트 분야", "테스트 분야 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                POPULAR_THEME_ID, FIELD_ID, "POPULAR", "인기 테마", "인기 테마 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                OTHER_THEME_ID, FIELD_ID, "OTHER", "기타 테마", "기타 테마 설명");

        LocalDateTime now = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        insertArticle("popular-1", POPULAR_THEME_ID, now.minusMinutes(5), false);
        insertArticle("popular-2", POPULAR_THEME_ID, now.minusHours(2), false);
        insertArticle("deleted", POPULAR_THEME_ID, now.minusMinutes(10), true);
        insertArticle("other", OTHER_THEME_ID, now.minusHours(1), false);
    }

    private void insertArticle(String id, long themeId, LocalDateTime publishedAt, boolean deleted) {
        jdbcTemplate.update("""
                INSERT INTO article (
                    id, publisher_country_code, theme_id, publisher, url, original_title,
                    crawled_at, theme_relevance_score, issue_similarity, tone_score,
                    created_at, published_at, issue_assigned_at, deleted_at
                ) VALUES (?, ?, ?, 'publisher', ?, 'title', ?, 1, 1, 0, ?, ?, ?, ?)
                """,
                id, COUNTRY_CODE, themeId, "https://example.com/" + id,
                Timestamp.valueOf(publishedAt), Timestamp.valueOf(publishedAt),
                Timestamp.valueOf(publishedAt), Timestamp.valueOf(publishedAt),
                deleted ? Timestamp.valueOf(publishedAt) : null
        );
    }
}
