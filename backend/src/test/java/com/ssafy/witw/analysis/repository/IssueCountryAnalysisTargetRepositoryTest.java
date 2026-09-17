package com.ssafy.witw.analysis.repository;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.support.RepositoryTest;
import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@RepositoryTest
@Import(IssueCountryAnalysisTargetRepository.class)
class IssueCountryAnalysisTargetRepositoryTest extends TestContainerSupport {

    private static final LocalDateTime PERIOD_END = LocalDateTime.of(2026, 9, 17, 14, 0);
    private static final LocalDateTime PERIOD_START = PERIOD_END.minusHours(24);
    private static final long FIELD_ID = 940_001L;
    private static final long THEME_ID = 940_001L;
    private static final long FIRST_ISSUE_ID = 940_001L;
    private static final long SECOND_ISSUE_ID = 940_002L;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private IssueCountryAnalysisTargetRepository targetRepository;

    @Test
    void 고정된_24시간_창의_TopN에서_국가별_기사_10건_이상만_선정한다() {
        prepareData();

        List<Target> topOne = targetRepository.findTargets(PERIOD_START, PERIOD_END, 1, 10);
        List<Target> topTwo = targetRepository.findTargets(PERIOD_START, PERIOD_END, 2, 10);

        assertThat(topOne).containsExactly(new Target(FIRST_ISSUE_ID, "ZX", 10));
        assertThat(topTwo).containsExactly(
                new Target(FIRST_ISSUE_ID, "ZX", 10),
                new Target(SECOND_ISSUE_ID, "ZX", 11)
        );
    }

    private void prepareData() {
        jdbcTemplate.update("INSERT INTO country (country_code, name_ko, name_en) VALUES ('ZX', '분석국가1', 'Analysis 1')");
        jdbcTemplate.update("INSERT INTO country (country_code, name_ko, name_en) VALUES ('ZY', '분석국가2', 'Analysis 2')");
        jdbcTemplate.update("INSERT INTO field (id, code, name, description) VALUES (?, 'ANALYSIS_FIELD', '분석 분야', '분석 분야')", FIELD_ID);
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, 'ANALYSIS_THEME', '분석 테마', '분석 테마')", THEME_ID, FIELD_ID);
        jdbcTemplate.update("INSERT INTO issue (id, theme_id, name) VALUES (?, ?, '분석 이슈 1')", FIRST_ISSUE_ID, THEME_ID);
        jdbcTemplate.update("INSERT INTO issue (id, theme_id, name) VALUES (?, ?, '분석 이슈 2')", SECOND_ISSUE_ID, THEME_ID);

        for (int index = 0; index < 10; index++) {
            insertArticle("first-zx-" + index, FIRST_ISSUE_ID, "ZX", PERIOD_START.plusMinutes(index), false);
        }
        for (int index = 0; index < 9; index++) {
            insertArticle("first-zy-" + index, FIRST_ISSUE_ID, "ZY", PERIOD_START.plusMinutes(index), false);
        }
        for (int index = 0; index < 11; index++) {
            insertArticle("second-zx-" + index, SECOND_ISSUE_ID, "ZX", PERIOD_START.plusMinutes(index), false);
        }
        insertArticle("deleted-first", FIRST_ISSUE_ID, "ZX", PERIOD_START.plusHours(1), true);
        insertArticle("before-start", FIRST_ISSUE_ID, "ZX", PERIOD_START.minusSeconds(1), false);
        insertArticle("at-end", FIRST_ISSUE_ID, "ZX", PERIOD_END, false);
    }

    private void insertArticle(String id, long issueId, String countryCode,
                               LocalDateTime publishedAt, boolean deleted) {
        Timestamp published = Timestamp.valueOf(publishedAt);
        jdbcTemplate.update("""
                INSERT INTO article (
                    id, publisher_country_code, theme_id, issue_id, publisher, url,
                    original_title, crawled_at, theme_relevance_score, issue_similarity,
                    tone_score, created_at, published_at, issue_assigned_at, deleted_at
                ) VALUES (?, ?, ?, ?, 'publisher', ?, 'title', ?, 1, 1, 50, ?, ?, ?, ?)
                """,
                id, countryCode, THEME_ID, issueId, "https://example.com/" + id,
                published, published, published, published,
                deleted ? published : null
        );
    }
}
