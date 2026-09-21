package com.ssafy.witw.domain.article.dao;

import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
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
@Import(NewsArticleQueryRepository.class)
class TimeMachineRepositoryTest extends TestContainerSupport {
    private static final long ID = 980_001L;
    private static final LocalDateTime AS_OF = LocalDateTime.of(2025, 9, 16, 10, 50);

    @Autowired private JdbcTemplate jdbc;
    @Autowired private ArticleRepository articles;
    @Autowired private IssueRepository issues;
    @Autowired private ThemeRepository themes;
    @Autowired private NewsArticleQueryRepository news;

    @BeforeEach
    void prepare() {
        jdbc.update("INSERT INTO field (id, code, name, description) VALUES (?, 'TIME_TEST', '시간 테스트', '설명')", ID);
        jdbc.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, 'TIME_TEST', '시간 테마', '설명')", ID, ID);
        jdbc.update("INSERT INTO issue (id, theme_id, name, created_at) VALUES (?, ?, '시간 이슈', ?)",
                ID, ID, Timestamp.valueOf(AS_OF.minusDays(2)));
    }

    @Test
    void distinguishesPublicationStorageAssignmentAndDeletionTimes() {
        insert("visible", AS_OF.minusHours(1), AS_OF.minusHours(1), AS_OF.minusMinutes(30), null);
        insert("late-storage", AS_OF.minusHours(1), AS_OF.plusMinutes(1), AS_OF.plusMinutes(2), null);
        insert("late-assignment", AS_OF.minusHours(1), AS_OF.minusHours(1), AS_OF.plusMinutes(1), null);
        insert("future-publication", AS_OF.plusMinutes(1), AS_OF.minusHours(1), AS_OF.minusMinutes(30), null);
        insert("deleted-later", AS_OF.minusHours(1), AS_OF.minusHours(1), AS_OF.minusMinutes(30), AS_OF.plusMinutes(1));
        insert("deleted-at-cutoff", AS_OF.minusHours(1), AS_OF.minusHours(1), AS_OF.minusMinutes(30), AS_OF);
        insert("lower-bound", AS_OF.minusHours(24), AS_OF.minusHours(24), AS_OF.minusHours(24), null);
        insert("upper-bound", AS_OF, AS_OF, AS_OF, null);
        insert("older", AS_OF.minusHours(25), AS_OF.minusHours(25), AS_OF.minusHours(25), null);

        assertThat(articles.countArticlesLast24Hours("KR", null, AS_OF)).isEqualTo(4);
        assertThat(articles.countArticlesLast24Hours("KR", ID, AS_OF)).isEqualTo(3);
        assertThat(articles.countVisibleAt(AS_OF)).isEqualTo(5);
        assertThat(issues.findIssueById(ID, AS_OF).articleCount()).isEqualTo(4);
        assertThat(articles.getRepresentArticlesByIssueId(ID, 10, AS_OF))
                .extracting(ArticleRepository.RepresentArticleProjection::getArticleId)
                .containsExactlyInAnyOrder("visible", "deleted-later", "lower-bound");
        assertThat(news.findVisibleById("late-storage", AS_OF)).isEmpty();
        assertThat(news.findVisibleById("deleted-later", AS_OF)).isPresent();
        assertThat(news.search("KR", null, null, AS_OF.minusHours(2), AS_OF.plusDays(1), 1, 10, AS_OF)
                .totalElements()).isEqualTo(3);
    }

    @Test
    void hourlyChartKeeps24BucketsButExcludesArticlesAfterSelectedMinute() {
        insert("before", AS_OF.minusMinutes(5), AS_OF.minusMinutes(5), AS_OF.minusMinutes(5), null);
        insert("after", AS_OF.plusMinutes(5), AS_OF.minusMinutes(5), AS_OF.minusMinutes(5), null);

        var rows = themes.findPopularThemesWithHourlyTrend("KR", 3, AS_OF);
        assertThat(rows).hasSize(24);
        assertThat(rows).allSatisfy(row -> assertThat(row.getArticleCount24()).isEqualTo(1));
        assertThat(rows.stream().mapToLong(ThemeRepository.PopularThemeTrendRow::getArticleCount).sum()).isEqualTo(1);
    }

    @Test
    void issueCreatedAfterSelectedTimeIsNotVisible() {
        jdbc.update("UPDATE issue SET created_at = ? WHERE id = ?", Timestamp.valueOf(AS_OF.plusMinutes(1)), ID);
        assertThat(issues.findIssueById(ID, AS_OF)).isNull();
        assertThat(issues.getIssuePreviewByIssueId(ID, AS_OF)).isNull();
    }

    private void insert(String id, LocalDateTime published, LocalDateTime created,
                        LocalDateTime assigned, LocalDateTime deleted) {
        jdbc.update("""
                INSERT INTO article (id, publisher_country_code, theme_id, issue_id, publisher,
                    url, original_title, theme_relevance_score, tone_score, issue_similarity,
                    published_at, created_at, crawled_at, issue_assigned_at, deleted_at)
                VALUES (?, 'KR', ?, ?, 'publisher', 'https://example.com', 'title', 0.5, 50, 0.5, ?, ?, ?, ?, ?)
                """, id, ID, ID, Timestamp.valueOf(published), Timestamp.valueOf(created),
                Timestamp.valueOf(created), Timestamp.valueOf(assigned), deleted == null ? null : Timestamp.valueOf(deleted));
    }
}
