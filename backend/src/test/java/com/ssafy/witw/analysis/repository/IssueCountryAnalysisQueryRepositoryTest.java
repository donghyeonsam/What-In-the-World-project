package com.ssafy.witw.analysis.repository;

import com.ssafy.witw.support.RepositoryTest;
import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;

@RepositoryTest
@Import(IssueCountryAnalysisQueryRepository.class)
class IssueCountryAnalysisQueryRepositoryTest extends TestContainerSupport {
    private static final long ID = 949_200;
    private static final LocalDateTime CREATED = LocalDateTime.of(2026, 9, 18, 8, 0);

    @Autowired JdbcTemplate jdbc;
    @Autowired IssueCountryAnalysisQueryRepository repository;

    @BeforeEach
    void seed() {
        jdbc.update("INSERT INTO country (country_code, name_ko, name_en) VALUES ('ZQ', '테스트 국가 1', 'Test country 1')");
        jdbc.update("INSERT INTO country (country_code, name_ko, name_en) VALUES ('ZR', '테스트 국가 2', 'Test country 2')");
        jdbc.update("INSERT INTO field (id, code, name, description) VALUES (?, 'ANALYSIS_QUERY_TEST', '분야', '분야')", ID);
        jdbc.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, 'ANALYSIS_QUERY_TEST', '테마', '테마')", ID, ID);
        jdbc.update("INSERT INTO issue (id, theme_id, name, created_at) VALUES (?, ?, '테스트 이슈', ?)", ID, ID, Timestamp.valueOf(CREATED));
        insert("ZQ", "이전", CREATED.plusHours(1));
        insert("ZQ", "최신", CREATED.plusHours(2));
        insert("ZQ", "미래", CREATED.plusHours(4));
        insert("ZR", "다른 국가", CREATED.plusHours(1));
    }

    @Test
    void finds_latest_per_country_without_leaking_future_results() {
        var asOf = CREATED.plusHours(3);

        assertThat(repository.issueExistsAt(ID, CREATED.minusSeconds(1))).isFalse();
        assertThat(repository.issueExistsAt(ID, asOf)).isTrue();
        assertThat(repository.analysisExistsAt(ID, "ZQ", CREATED.plusMinutes(30))).isFalse();
        assertThat(repository.analysisExistsAt(ID, "ZQ", asOf)).isTrue();
        assertThat(repository.analysisExistsAt(ID, "ZR", asOf)).isTrue();
        assertThat(repository.analysisExistsAt(ID, "ZZ", asOf)).isFalse();
        assertThat(repository.findLatestByIssue(ID, asOf))
                .extracting(IssueCountryAnalysisQueryRepository.AnalysisRow::title)
                .containsExactly("최신", "다른 국가");
        assertThat(repository.findLatestByIssueAndCountry(ID, "ZQ", asOf)).get()
                .extracting(IssueCountryAnalysisQueryRepository.AnalysisRow::title)
                .isEqualTo("최신");
        assertThat(repository.findLatestByIssueAndCountry(ID, "ZQ", CREATED.plusMinutes(30))).isEmpty();
        assertThat(repository.findLatestByIssue(ID + 1, asOf)).isEmpty();
    }

    private void insert(String countryCode, String title, LocalDateTime createdAt) {
        jdbc.update("""
                INSERT INTO issue_country_analysis
                    (issue_id, country_code, title, summary, details, article_count, created_at)
                VALUES (?, ?, ?, '요약', '["관점"]', 15, ?)
                """, ID, countryCode, title, Timestamp.valueOf(createdAt));
    }
}
