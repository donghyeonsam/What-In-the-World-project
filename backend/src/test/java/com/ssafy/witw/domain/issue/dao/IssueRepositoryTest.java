package com.ssafy.witw.domain.issue.dao;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace.NONE;

@DataJpaTest
@AutoConfigureTestDatabase(replace = NONE)
class IssueRepositoryTest {

    private static final long FIELD_ID = 920_001L;
    private static final long THEME_ID = 920_001L;
    private static final long OTHER_THEME_ID = 920_002L;
    private static final long POPULAR_ISSUE_ID = 920_001L;
    private static final long OTHER_ISSUE_ID = 920_002L;
    private static final String COUNTRY_CODE = "ZX";

    @Autowired
    private IssueRepository issueRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void 기사량이_많은_주요_이슈를_테마별로_상위_개수만큼_조회한다() {
        // given
        prepareData();

        // when
        List<IssueRepository.PrimaryIssue> issues =
                issueRepository.getPrimaryIssuesByThemeId(THEME_ID, 1);

        // then
        assertThat(issues)
                .as("테마별 주요 이슈 조회 결과")
                .hasSize(1);
        assertThat(issues.getFirst().getIssueId())
                .as("기사량이 가장 많은 이슈가 첫 번째로 조회됨")
                .isEqualTo(POPULAR_ISSUE_ID);
        assertThat(issues.getFirst().getIssueTitle())
                .as("주요 이슈 제목이 projection에 매핑됨")
                .isEqualTo("가장 인기 있는 이슈");
    }

    private void prepareData() {
        jdbcTemplate.update("INSERT INTO country VALUES (?, ?, ?)", COUNTRY_CODE, "테스트 국가", "Test Country");
        jdbcTemplate.update("INSERT INTO field (id, code, name, description) VALUES (?, ?, ?, ?)",
                FIELD_ID, "ISSUE_TEST", "이슈 테스트 분야", "이슈 테스트 분야 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                THEME_ID, FIELD_ID, "ISSUE_THEME", "이슈 테마", "이슈 테마 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                OTHER_THEME_ID, FIELD_ID, "OTHER_ISSUE_THEME", "다른 테마", "다른 테마 설명");
        insertIssue(POPULAR_ISSUE_ID, THEME_ID, "가장 인기 있는 이슈");
        insertIssue(OTHER_ISSUE_ID, THEME_ID, "두 번째 이슈");
        insertIssue(920_003L, OTHER_THEME_ID, "다른 테마 이슈");

        LocalDateTime now = LocalDateTime.now();
        insertArticle("popular-1", THEME_ID, POPULAR_ISSUE_ID, now, false);
        insertArticle("popular-2", THEME_ID, POPULAR_ISSUE_ID, now, false);
        insertArticle("other-issue", THEME_ID, OTHER_ISSUE_ID, now, false);
        insertArticle("deleted-popular", THEME_ID, POPULAR_ISSUE_ID, now, true);
        insertArticle("other-theme", OTHER_THEME_ID, 920_003L, now, false);
    }

    private void insertIssue(long id, long themeId, String name) {
        jdbcTemplate.update("INSERT INTO issue (id, theme_id, name) VALUES (?, ?, ?)", id, themeId, name);
    }

    private void insertArticle(String id, long themeId, long issueId,
                               LocalDateTime publishedAt, boolean deleted) {
        jdbcTemplate.update("""
                INSERT INTO article (
                    id, publisher_country_code, theme_id, issue_id, publisher, url,
                    original_title, crawled_at, theme_relevance_score, issue_similarity,
                    tone_score, created_at, published_at, issue_assigned_at, deleted_at
                ) VALUES (?, ?, ?, ?, 'publisher', ?, 'title', ?, 1, 1, 50, ?, ?, ?, ?)
                """,
                id, COUNTRY_CODE, themeId, issueId, "https://example.com/" + id,
                Timestamp.valueOf(publishedAt), Timestamp.valueOf(publishedAt),
                Timestamp.valueOf(publishedAt), Timestamp.valueOf(publishedAt),
                deleted ? Timestamp.valueOf(publishedAt) : null);
    }
}
