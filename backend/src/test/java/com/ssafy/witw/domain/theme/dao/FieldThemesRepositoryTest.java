package com.ssafy.witw.domain.theme.dao;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace.NONE;

@DataJpaTest
@AutoConfigureTestDatabase(replace = NONE)
class FieldThemesRepositoryTest {
    @Autowired private ThemeRepository repository;
    @Autowired private JdbcTemplate jdbc;

    @Test
    @DisplayName("[분야별 테마 집계] 최근 24시간의 미삭제 기사만 집계하고 기사 없는 테마와 빈 분야도 조회한다")
    void 최근_24시간의_미삭제_기사만_집계하고_빈_테마와_분야도_조회한다() {
        // given
        LocalDateTime now = jdbc.queryForObject(
                "SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul'", LocalDateTime.class);
        jdbc.update("""
                INSERT INTO country (country_code, name_ko, name_en, longitude, latitude)
                VALUES ('ZX', 'Test', 'Test', 0, 0)
                """);
        jdbc.update("""
                INSERT INTO field (id, code, name, description)
                VALUES (940001, 'FIELD_TEST_A', 'Field A', 'Test'),
                       (940002, 'FIELD_TEST_B', 'Field B', 'Test')
                """);
        jdbc.update("""
                INSERT INTO theme (id, field_id, code, name, description)
                VALUES (940001, 940001, 'FIELD_THEME_A', 'Theme A', 'Test'),
                       (940002, 940001, 'FIELD_THEME_B', 'Theme B', 'Test')
                """);
        // 24시간 전 경계는 포함하고 현재 시각 이상, 24시간 이전, 삭제된 기사는 제외한다.
        insertArticle("recent", now.minusHours(1), false);
        insertArticle("lower-bound", now.minusHours(24), false);
        insertArticle("too-old", now.minusHours(24).minusSeconds(1), false);
        insertArticle("upper-bound", now, false);
        insertArticle("future", now.plusHours(1), false);
        insertArticle("deleted", now.minusHours(1), true);

        // when
        var rows = repository.findThemesByField();

        // then
        assertThat(rows.stream()
                .filter(row -> row.getFieldId() == 940001L || row.getFieldId() == 940002L))
                .as("기간 내 미삭제 기사 2건을 집계하고, 기사 없는 테마와 테마 없는 분야는 0건으로 유지한다")
                .extracting(ThemeRepository.FieldThemeRow::getFieldId,
                        ThemeRepository.FieldThemeRow::getThemeId,
                        ThemeRepository.FieldThemeRow::getThemeName,
                        ThemeRepository.FieldThemeRow::getArticleCount24)
                .containsExactly(tuple(940001L, 940001L, "Theme A", 2L),
                        tuple(940001L, 940002L, "Theme B", 0L),
                        tuple(940002L, null, null, 0L));
    }

    private void insertArticle(String id, LocalDateTime publishedAt, boolean deleted) {
        jdbc.update("""
                INSERT INTO article (id, publisher_country_code, theme_id, publisher, url,
                    original_title, crawled_at, theme_relevance_score, issue_similarity,
                    tone_score, created_at, published_at, issue_assigned_at, deleted_at)
                VALUES (?, 'ZX', 940001, 'Test', ?, 'Test', ?, 1, 1, 50, ?, ?, ?, ?)
                """, "field-" + id, "https://example.com/field-" + id,
                publishedAt, publishedAt, publishedAt, publishedAt, deleted ? publishedAt : null);
    }
}
