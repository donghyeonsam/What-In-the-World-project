package com.ssafy.witw.domain.article.dao;

import com.ssafy.witw.domain.article.entity.Article;
import org.junit.jupiter.api.DisplayName;
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
class ArticleRepositoryTest {

    private static final long FIELD_ID = 910_001L;
    private static final long THEME_ID = 910_001L;
    private static final long OTHER_THEME_ID = 910_002L;
    private static final String COUNTRY_CODE = "ZY";

    @Autowired
    private ArticleRepository articleRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void 테마와_가장_유사하고_삭제되지_않은_기사만_상위_개수만큼_조회한다() {
        // given
        prepareData();

        // when
        List<ArticleRepository.RepresentArticleProjection> articles =
                articleRepository.getRepresentArticlesByThemeId(THEME_ID, 2);

        // then
        assertThat(articles)
                .as("테마별 대표 기사 조회 결과")
                .hasSize(2);
        assertThat(articles.get(0).getArticleId())
                .as("유사도가 가장 높은 기사가 첫 번째로 조회됨")
                .isEqualTo("represent-1");
        assertThat(articles.get(0).getArticleTitle())
                .as("대표 기사의 제목이 projection에 매핑됨")
                .isEqualTo("가장 유사한 기사");
        assertThat(articles.get(0).getPublishedAt())
                .as("대표 기사의 발행 시각이 projection에 매핑됨")
                .isNotNull();
        assertThat(articles)
                .as("삭제된 기사와 다른 테마의 기사는 조회에서 제외됨")
                .extracting(ArticleRepository.RepresentArticleProjection::getArticleId)
                .containsExactly("represent-1", "represent-2");
    }

    @Test
    @DisplayName("[미분류 기사 저장] 이슈가 없으면 이슈 유사도와 배정 시각도 null로 저장한다")
    void 이슈가_없으면_이슈_유사도와_배정_시각도_null로_저장한다() {
        // given
        prepareData();
        LocalDateTime now = LocalDateTime.now();
        jdbcTemplate.update("""
                INSERT INTO article (
                    id, publisher_country_code, theme_id, publisher, url, original_title,
                    crawled_at, theme_relevance_score, tone_score, created_at, published_at
                ) VALUES ('unassigned-article', ?, ?, 'publisher', 'https://example.com/unassigned',
                          '미분류 기사', ?, 1, 50, ?, ?)
                """, COUNTRY_CODE, THEME_ID, Timestamp.valueOf(now), Timestamp.valueOf(now),
                Timestamp.valueOf(now));

        // when
        Article article = articleRepository.findById("unassigned-article").orElseThrow();

        // then
        assertThat(article.getIssue()).as("배정된 이슈").isNull();
        assertThat(article.getIssueSimilarity()).as("이슈 유사도").isNull();
        assertThat(article.getIssueAssignedAt()).as("이슈 배정 시각").isNull();
    }

    private void prepareData() {
        jdbcTemplate.update("INSERT INTO country VALUES (?, ?, ?)", COUNTRY_CODE, "테스트 국가", "Test Country");
        jdbcTemplate.update("INSERT INTO field (id, code, name, description) VALUES (?, ?, ?, ?)",
                FIELD_ID, "ARTICLE_TEST", "기사 테스트 분야", "기사 테스트 분야 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                THEME_ID, FIELD_ID, "ARTICLE_THEME", "기사 테마", "기사 테마 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                OTHER_THEME_ID, FIELD_ID, "OTHER_ARTICLE_THEME", "다른 테마", "다른 테마 설명");

        LocalDateTime now = LocalDateTime.now();
        insertArticle("represent-1", THEME_ID, "가장 유사한 기사", 0.95, now, false);
        insertArticle("represent-2", THEME_ID, "두 번째 유사 기사", 0.80, now.minusMinutes(1), false);
        insertArticle("deleted-article", THEME_ID, "삭제된 기사", 1.00, now, true);
        insertArticle("other-theme-article", OTHER_THEME_ID, "다른 테마 기사", 1.00, now, false);
    }

    private void insertArticle(String id, long themeId, String title, double relevance,
                                LocalDateTime publishedAt, boolean deleted) {
        jdbcTemplate.update("""
                INSERT INTO article (
                    id, publisher_country_code, theme_id, publisher, url, original_title,
                    translated_title, crawled_at, theme_relevance_score, issue_similarity,
                    tone_score, created_at, published_at, issue_assigned_at, deleted_at
                ) VALUES (?, ?, ?, 'publisher', ?, ?, ?, ?, ?, 1, 50, ?, ?, ?, ?)
                """,
                id, COUNTRY_CODE, themeId, "https://example.com/" + id, title, title,
                Timestamp.valueOf(publishedAt), relevance, Timestamp.valueOf(publishedAt),
                Timestamp.valueOf(publishedAt), Timestamp.valueOf(publishedAt),
                deleted ? Timestamp.valueOf(publishedAt) : null);
    }
}
