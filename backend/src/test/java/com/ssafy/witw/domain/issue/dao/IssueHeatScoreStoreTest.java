package com.ssafy.witw.domain.issue.dao;

import com.ssafy.witw.support.RepositoryTest;
import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@RepositoryTest
class IssueHeatScoreStoreTest extends TestContainerSupport {

    private static final long FIELD_ID = 930_001L;
    private static final long THEME_ID = 930_001L;
    private static final long MASS_ISSUE_ID = 930_001L;
    private static final long SPREAD_ISSUE_ID = 930_002L;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private IssueHeatScoreStore scoreStore;

    @BeforeEach
    void setUp() {
        scoreStore = new IssueHeatScoreStore(jdbcTemplate);
        prepareData();
    }

    @Test
    void 국가별_상대_점수와_국가_확산도를_계층적으로_계산한다() {
        // when
        LocalDateTime calculatedAt = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        int countryRows = scoreStore.appendCountryScores(calculatedAt);
        int globalRows = scoreStore.appendGlobalScores(calculatedAt);

        // then
        assertThat(countryRows).isEqualTo(4);
        assertThat(globalRows).isEqualTo(2);

        Map<String, Object> mass = globalScore(MASS_ISSUE_ID, calculatedAt);
        Map<String, Object> spread = globalScore(SPREAD_ISSUE_ID, calculatedAt);

        assertThat(((Number) mass.get("country_count")).longValue()).isEqualTo(1);
        assertThat(((Number) spread.get("country_count")).longValue()).isEqualTo(3);
        assertThat(((Number) spread.get("global_heat_score")).doubleValue())
                .as("기사 수가 더 적어도 여러 국가와 언론사로 확산된 이슈가 더 높아야 한다")
                .isGreaterThan(((Number) mass.get("global_heat_score")).doubleValue());

        jdbcTemplate.queryForList("SELECT * FROM issue_country_heat_score")
                .forEach(row -> {
                    assertThat(((Number) row.get("local_heat_score")).doubleValue())
                            .isBetween(0.0, 100.0);
                    assertThat(row.keySet()).containsExactlyInAnyOrder(
                            "id",
                            "issue_id",
                            "country_code",
                            "calculated_at",
                            "score_version",
                            "local_heat_score"
                    );
                });
    }

    @Test
    void 기존_점수를_삭제하지_않고_스냅샷을_누적한다() {
        LocalDateTime firstSnapshot = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        LocalDateTime secondSnapshot = firstSnapshot.plusMinutes(5);

        scoreStore.appendCountryScores(firstSnapshot);
        scoreStore.appendGlobalScores(firstSnapshot);
        scoreStore.appendCountryScores(secondSnapshot);
        scoreStore.appendGlobalScores(secondSnapshot);

        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM issue_country_heat_score", Long.class)).isEqualTo(8L);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM issue_global_heat_score", Long.class)).isEqualTo(4L);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(DISTINCT calculated_at) FROM issue_global_heat_score", Long.class))
                .isEqualTo(2L);
    }

    private Map<String, Object> globalScore(long issueId, LocalDateTime calculatedAt) {
        return jdbcTemplate.queryForMap(
                "SELECT * FROM issue_global_heat_score WHERE issue_id = ? AND calculated_at = ?",
                issueId,
                Timestamp.valueOf(calculatedAt)
        );
    }

    private void prepareData() {
        insertCountry("ZX", "테스트X국", "Test X");
        insertCountry("ZY", "테스트Y국", "Test Y");
        insertCountry("ZZ", "테스트Z국", "Test Z");
        jdbcTemplate.update(
                "INSERT INTO field (id, code, name, description) VALUES (?, 'HEAT', '열기', '열기 점수')",
                FIELD_ID
        );
        jdbcTemplate.update(
                "INSERT INTO theme (id, field_id, code, name, description) "
                        + "VALUES (?, ?, 'HEAT_THEME', '열기 테마', '열기 점수 테스트')",
                THEME_ID,
                FIELD_ID
        );
        jdbcTemplate.update(
                "INSERT INTO issue (id, theme_id, name) VALUES (?, ?, '단일국가 대량이슈')",
                MASS_ISSUE_ID,
                THEME_ID
        );
        jdbcTemplate.update(
                "INSERT INTO issue (id, theme_id, name) VALUES (?, ?, '다국가 확산이슈')",
                SPREAD_ISSUE_ID,
                THEME_ID
        );

        LocalDateTime now = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        for (int index = 0; index < 8; index++) {
            insertArticle(
                    "mass-" + index,
                    MASS_ISSUE_ID,
                    "ZX",
                    "mass.example",
                    now.minusMinutes(20L + index)
            );
        }

        String[] countries = {"ZX", "ZY", "ZZ"};
        int sequence = 0;
        for (String country : countries) {
            insertArticle(
                    "spread-" + sequence++,
                    SPREAD_ISSUE_ID,
                    country,
                    country.toLowerCase() + "-one.example",
                    now.minusMinutes(10)
            );
            insertArticle(
                    "spread-" + sequence++,
                    SPREAD_ISSUE_ID,
                    country,
                    country.toLowerCase() + "-two.example",
                    now.minusHours(5)
            );
        }
    }

    private void insertCountry(String code, String nameKo, String nameEn) {
        jdbcTemplate.update(
                "INSERT INTO country (country_code, name_ko, name_en) VALUES (?, ?, ?)",
                code,
                nameKo,
                nameEn
        );
    }

    private void insertArticle(
            String id,
            long issueId,
            String countryCode,
            String publisher,
            LocalDateTime publishedAt
    ) {
        Timestamp timestamp = Timestamp.valueOf(publishedAt);
        jdbcTemplate.update("""
                        INSERT INTO article (
                            id, publisher_country_code, theme_id, issue_id, publisher, url,
                            original_title, crawled_at, theme_relevance_score, issue_similarity,
                            tone_score, created_at, published_at, issue_assigned_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'title', ?, 1, 1, 0, ?, ?, ?)
                        """,
                id,
                countryCode,
                THEME_ID,
                issueId,
                publisher,
                "https://example.com/" + id,
                timestamp,
                timestamp,
                timestamp,
                timestamp
        );
    }
}
