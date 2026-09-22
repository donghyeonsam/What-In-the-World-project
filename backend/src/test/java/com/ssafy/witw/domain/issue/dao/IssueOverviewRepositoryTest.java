package com.ssafy.witw.domain.issue.dao;

import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.support.RepositoryTest;
import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.assertj.core.api.Assertions.within;

@RepositoryTest
class IssueOverviewRepositoryTest extends TestContainerSupport {
    private static final long THEME_ID = 930_001L;
    private static final long ISSUE_ID = 930_001L;
    private static final long OTHER_ISSUE_ID = 930_002L;
    @Autowired private IssueRepository issueRepository;
    @Autowired private ArticleRepository articleRepository;
    @Autowired private JdbcTemplate jdbcTemplate;
    private LocalDateTime now;

    @BeforeEach
    void 기본_테마와_이슈와_국가를_준비한다() {
        now = jdbcTemplate.queryForObject(
                "SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul'", LocalDateTime.class);
        jdbcTemplate.update("""
                INSERT INTO country (country_code, name_ko, name_en, longitude, latitude)
                VALUES ('ZQ', '테스트A국', 'Test A', 127, 37.5),
                       ('ZR', '테스트B국', 'Test B', 139, 35)
                """);
        jdbcTemplate.update("INSERT INTO field (id, code, name, description) VALUES (?, 'OVERVIEW', '분야', '설명')", THEME_ID);
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, 'OVERVIEW', '기후', '설명')", THEME_ID, THEME_ID);
        jdbcTemplate.update("INSERT INTO issue (id, theme_id, name) VALUES (?, ?, '폭염'), (?, ?, '다른 이슈')",
                ISSUE_ID, THEME_ID, OTHER_ISSUE_ID, THEME_ID);
    }

    @Test
    void 프리뷰는_해당_이슈의_삭제되지_않은_전체_기사_수를_반환한다() {
        // given
        기사추가("preview-recent", ISSUE_ID, "ZQ", 20, 0.7, now.minusHours(1), false);
        기사추가("preview-old", ISSUE_ID, "ZQ", 80, 0.9, now.minusDays(2), false);
        기사추가("preview-deleted", ISSUE_ID, "ZQ", 90, 1, now.minusHours(1), true);
        기사추가("preview-other", OTHER_ISSUE_ID, "ZR", 90, 1, now.minusHours(1), false);

        // when
        var preview = issueRepository.getIssuePreviewByIssueId(ISSUE_ID);

        // then
        assertThat(preview).as("존재하는 이슈의 프리뷰").isNotNull();
        assertThat(preview.getIssueTitle()).as("이슈 제목 alias 매핑").isEqualTo("폭염");
        assertThat(preview.getThemeTitle()).as("테마 제목 alias 매핑").isEqualTo("기후");
        assertThat(preview.getArticleCount()).as("삭제 및 다른 이슈 기사 제외, 24시간 이전 기사는 포함").isEqualTo(2L);
    }

    @Test
    void 기사_없는_이슈와_삭제된_기사만_있는_이슈는_기사_수가_영이다() {
        // given
        기사추가("only-deleted", OTHER_ISSUE_ID, "ZQ", 90, 1, now.minusHours(1), true);

        // when
        var empty = issueRepository.getIssuePreviewByIssueId(ISSUE_ID);
        var deletedOnly = issueRepository.getIssuePreviewByIssueId(OTHER_ISSUE_ID);
        var missing = issueRepository.getIssuePreviewByIssueId(930_099L);

        // then
        assertThat(empty).as("기사가 없어도 이슈 정보는 조회됨").isNotNull();
        assertThat(empty.getArticleCount()).as("LEFT JOIN의 빈 행을 기사로 세지 않음").isZero();
        assertThat(deletedOnly.getArticleCount()).as("삭제된 기사만 있는 경우 기사 수").isZero();
        assertThat(missing).as("존재하지 않는 이슈는 프리뷰 없음").isNull();
    }

    @Test
    void 국가_톤은_최근_24시간_경계와_삭제_여부를_적용하고_국가별로_집계한다() {
        // given
        기사추가("tone-start", ISSUE_ID, "ZQ", 20, 0.5, now.minusHours(24), false);
        기사추가("tone-recent", ISSUE_ID, "ZQ", 80, 0.5, now.minusHours(1), false);
        기사추가("tone-country-b", ISSUE_ID, "ZR", 10, 0.5, now.minusHours(1), false);
        기사추가("tone-old", ISSUE_ID, "ZQ", 100, 0.5, now.minusHours(24).minusSeconds(1), false);
        기사추가("tone-end", ISSUE_ID, "ZQ", 100, 0.5, now, false);
        기사추가("tone-deleted", ISSUE_ID, "ZQ", 100, 0.5, now.minusHours(1), true);
        기사추가("tone-other", OTHER_ISSUE_ID, "ZQ", 100, 0.5, now.minusHours(1), false);

        // when
        var tones = issueRepository.findCountryTonesLast24Hours(ISSUE_ID, now);

        // then
        assertThat(tones).as("발행 국가별로 평균 내림차순 조회")
                .extracting(IssueRepository.CountryToneRow::getCountryCode).containsExactly("ZQ", "ZR");
        var first = tones.getFirst();
        assertThat(first.getCountryName()).as("국가 한글 이름 매핑").isEqualTo("테스트A국");
        assertThat(first.getLongitude()).as("경도 매핑").isEqualTo(127);
        assertThat(first.getLatitude()).as("위도 매핑").isEqualTo(37.5);
        assertThat(first.getToneAvg()).as("24시간 시작 포함, 끝 제외 및 삭제·다른 이슈 제외 후 평균")
                .isCloseTo(50, within(1e-9));
        assertThat(first.getToneMin()).as("유효 기사 최소 톤").isEqualTo(20);
        assertThat(first.getToneMax()).as("유효 기사 최대 톤").isEqualTo(80);
        assertThat(tones.get(1).getToneAvg()).as("다른 국가의 톤은 별도 집계").isEqualTo(10);
    }

    @Test
    void 대표_기사는_이슈_유사도와_동점시_아이디_순으로_제한하여_조회한다() {
        // given
        기사추가("rep-low", ISSUE_ID, "ZQ", 20, 0.1, now.minusHours(1), false);
        기사추가("rep-b", ISSUE_ID, "ZQ", 66, 0.9, now.minusHours(1), false);
        기사추가("rep-a", ISSUE_ID, "ZR", 33, 0.9, now.minusHours(2), false);
        기사추가("rep-deleted", ISSUE_ID, "ZQ", 99, 1, now.minusHours(1), true);
        기사추가("rep-other", OTHER_ISSUE_ID, "ZQ", 99, 1, now.minusHours(1), false);
        // 테마 유사도와 이슈 유사도가 반대 순서가 되도록 설정
        jdbcTemplate.update("UPDATE article SET theme_relevance_score = 1 WHERE id = 'rep-low'");

        // when
        var articles = articleRepository.getRepresentArticlesByIssueId(ISSUE_ID, 2, now);

        // then
        assertThat(articles).as("삭제·다른 이슈 제외, 이슈 유사도 내림차순 및 동점 ID 순, limit 적용")
                .extracting(ArticleRepository.RepresentArticleProjection::getArticleId)
                .containsExactly("rep-a", "rep-b");
        assertThat(articles).as("최근 24시간 대표 기사의 제목, 언론사, URL, 발행일 projection 매핑")
                .extracting(ArticleRepository.RepresentArticleProjection::getArticleTitle,
                        ArticleRepository.RepresentArticleProjection::getArticlePublisher,
                        ArticleRepository.RepresentArticleProjection::getUrl,
                        ArticleRepository.RepresentArticleProjection::getPublishedAt)
                .containsExactly(tuple("제목 rep-a", "언론사", "https://example.com/rep-a", now.minusHours(2)),
                        tuple("제목 rep-b", "언론사", "https://example.com/rep-b", now.minusHours(1)));
        assertThat(articles.getFirst().getArticleToneScore()).as("톤 점수 BigDecimal 매핑")
                .isEqualByComparingTo(new BigDecimal("33"));
    }

    @Test
    void 집계할_기사가_없으면_국가_톤과_대표_기사는_빈_목록이다() {
        // given: 기본 이슈에 기사 없음

        // when
        var tones = issueRepository.findCountryTonesLast24Hours(ISSUE_ID);
        var articles = articleRepository.getRepresentArticlesByIssueId(ISSUE_ID, 3);

        // then
        assertThat(tones).as("기사 없는 이슈의 국가 톤").isEmpty();
        assertThat(articles).as("기사 없는 이슈의 대표 기사").isEmpty();
    }

    private void 기사추가(String id, long issueId, String country, double tone,
                        double similarity, LocalDateTime publishedAt, boolean deleted) {
        jdbcTemplate.update("""
                INSERT INTO article (id, theme_id, issue_id, publisher_country_code,
                    publisher, url, original_title, translated_title, crawled_at,
                    theme_relevance_score, issue_similarity, tone_score, created_at,
                    published_at, issue_assigned_at, deleted_at)
                VALUES (?, ?, ?, ?, '언론사', ?, '원문', ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """, id, THEME_ID, issueId, country, "https://example.com/" + id,
                "제목 " + id, publishedAt, similarity, tone, publishedAt, publishedAt,
                publishedAt, deleted ? publishedAt : null);
    }
}
