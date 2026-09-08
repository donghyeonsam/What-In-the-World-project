package com.ssafy.witw.domain.issue.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.country.dto.CountryTone;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.dto.GlobalIssueDetailResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse.GlobalIssue;
import com.ssafy.witw.domain.issue.dto.IssueInfo;
import com.ssafy.witw.support.RepositoryTest;
import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

@RepositoryTest
class IssueServiceTest extends TestContainerSupport {

    private static final String COUNTRY_A = "ZA";
    private static final String COUNTRY_B = "ZB";
    private static final long FIELD_ID = 900_001L;
    private static final long THEME_ID = 900_001L;
    private static final long HOT_ISSUE_ID = 900_001L;
    private static final long MINOR_ISSUE_ID = 900_002L;
    private static final long OLD_ISSUE_ID = 900_003L;
    private static final long EMPTY_ISSUE_ID = 900_004L;
    private static final long NOT_EXIST_ISSUE_ID = 900_999L;

    // 픽스처가 넣는 기사 중 삭제되지 않은 기사 수 (24시간 밖 기사, 이슈 미배정 기사 포함)
    private static final long EXPECTED_TOTAL_ARTICLE_COUNT = 8;
    // 그중 최근 24시간 안에 들어오는 기사 수
    private static final long EXPECTED_RECENT_24_ARTICLE_COUNT = 6;

    @Autowired
    private IssueRepository issueRepository;

    @Autowired
    private ArticleRepository articleRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private IssueService issueService;

    @BeforeEach
    void setUp() {
        issueService = new IssueService(issueRepository, articleRepository);
        prepareData();
    }

    @Test
    void 최근_24시간_기사_수가_많은_순서로_이슈를_반환한다() {
        // when
        GlobalIssueRankResponse response = issueService.getGlobalIssueRank();

        // then
        assertThat(response.globalIssues())
                .as("24시간 밖 기사만 가진 이슈는 제외된다")
                .hasSize(2);
        assertThat(response.globalIssues())
                .extracting(GlobalIssue::issueId)
                .as("기사 수 내림차순 랭킹")
                .containsExactly(HOT_ISSUE_ID, MINOR_ISSUE_ID);

        GlobalIssue hot = response.globalIssues().getFirst();
        assertThat(hot.issueName()).isEqualTo("핫이슈");
        assertThat(hot.themeName()).isEqualTo("테스트 테마");
        assertThat(hot.fieldName()).isEqualTo("테스트 분야");
        assertThat(hot.articleCount())
                .as("삭제 기사와 이슈 미배정 기사를 제외한 24시간 기사 수")
                .isEqualTo(3);
        assertThat(hot.firstSeenAt()).as("이슈 최초 등장 시각").isNotNull();
    }

    @Test
    void 이슈_랭킹에_전체_기사_수와_최근_24시간_기사_수를_함께_반환한다() {
        // when
        GlobalIssueRankResponse response = issueService.getGlobalIssueRank();

        // then
        assertThat(response.totalArticleCount())
                .as("삭제 기사만 제외하고 24시간 밖 기사와 이슈 미배정 기사까지 센다")
                .isEqualTo(EXPECTED_TOTAL_ARTICLE_COUNT);
        assertThat(response.recent24ArticleCount())
                .as("24시간 밖 기사는 제외하고 이슈 미배정 기사는 센다")
                .isEqualTo(EXPECTED_RECENT_24_ARTICLE_COUNT);
    }

    @Test
    void 선택한_이슈의_기사_집계와_국가별_톤을_톤_평균_내림차순으로_반환한다() {
        // when
        GlobalIssueDetailResponse response = issueService.getGlobalIssueDetail(HOT_ISSUE_ID);

        // then
        IssueInfo issueInfo = response.issueInfo();
        assertThat(issueInfo.issueId()).isEqualTo(HOT_ISSUE_ID);
        assertThat(issueInfo.issueName()).isEqualTo("핫이슈");
        assertThat(issueInfo.articleCount())
                .as("삭제 기사를 제외한 기사 수")
                .isEqualTo(3);
        assertThat(issueInfo.countryCount())
                .as("중복을 제거한 발행 국가 수")
                .isEqualTo(2);

        List<CountryTone> countryTones = response.countryTones();
        assertThat(countryTones)
                .extracting(tone -> tone.country().countryCode())
                .as("톤 평균이 높은 국가부터")
                .containsExactly(COUNTRY_A, COUNTRY_B);

        CountryTone countryA = countryTones.getFirst();
        assertThat(countryA.country().countryName()).isEqualTo("테스트A국");
        assertThat(countryA.country().lat()).isEqualTo(37.5);
        assertThat(countryA.country().lng()).isEqualTo(127.0);
        assertThat(countryA.toneAvg())
                .as("삭제 기사의 톤 9.0을 제외한 (1.0 + 3.0) / 2")
                .isCloseTo(2.0, within(1e-9));
        assertThat(countryA.toneMax())
                .as("삭제 기사의 톤 9.0이 최댓값이 되면 안 된다")
                .isCloseTo(3.0, within(1e-9));
        assertThat(countryA.toneMin()).isCloseTo(1.0, within(1e-9));

        CountryTone countryB = countryTones.get(1);
        assertThat(countryB.toneAvg()).isCloseTo(-2.0, within(1e-9));
    }

    @Test
    void 선택한_이슈의_24시간_밖_기사는_톤_집계에서만_제외한다() {
        // when
        GlobalIssueDetailResponse response = issueService.getGlobalIssueDetail(OLD_ISSUE_ID);

        // then
        assertThat(response.countryTones())
                .as("30시간, 40시간 전 기사만 가진 이슈는 톤 집계 대상이 없다")
                .isEmpty();
        assertThat(response.issueInfo().articleCount())
                .as("기사 수는 24시간 제한 없이 집계한다")
                .isEqualTo(2);
        assertThat(response.issueInfo().countryCount()).isEqualTo(1);
    }

    @Test
    void 기사가_한_건도_없는_이슈도_집계가_영인_응답을_반환한다() {
        // when
        GlobalIssueDetailResponse response = issueService.getGlobalIssueDetail(EMPTY_ISSUE_ID);

        // then
        assertThat(response.issueInfo().issueName())
                .as("LEFT JOIN 이라 기사가 없어도 이슈 정보는 나온다")
                .isEqualTo("기사없는이슈");
        assertThat(response.issueInfo().articleCount()).isZero();
        assertThat(response.issueInfo().countryCount()).isZero();
        assertThat(response.countryTones()).isEmpty();
    }

    @Test
    void 존재하지_않는_이슈를_조회하면_ENTITY_NOT_FOUND_이다() {
        // when & then
        assertThatThrownBy(() -> issueService.getGlobalIssueDetail(NOT_EXIST_ISSUE_ID))
                .as("LEFT JOIN 결과가 null 인 경우만 미존재로 판정한다")
                .isInstanceOfSatisfying(GlobalException.class,
                        exception -> assertThat(exception.getErrorCode())
                                .as("이슈 없음 오류 코드")
                                .isEqualTo(ErrorCode.ENTITY_NOT_FOUND));
    }

    private void prepareData() {
        insertCountry(COUNTRY_A, "테스트A국", "Test A", 37.5, 127.0);
        insertCountry(COUNTRY_B, "테스트B국", "Test B", 35.0, 139.0);
        jdbcTemplate.update("INSERT INTO field (id, code, name, description) VALUES (?, ?, ?, ?)",
                FIELD_ID, "TEST", "테스트 분야", "테스트 분야 설명");
        jdbcTemplate.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
                THEME_ID, FIELD_ID, "TEST", "테스트 테마", "테스트 테마 설명");

        LocalDateTime now = LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        insertIssue(HOT_ISSUE_ID, "핫이슈", now.minusDays(3));
        insertIssue(MINOR_ISSUE_ID, "잔잔한이슈", now.minusDays(1));
        insertIssue(OLD_ISSUE_ID, "지난이슈", now.minusDays(10));
        insertIssue(EMPTY_ISSUE_ID, "기사없는이슈", now.minusDays(1));

        // 핫이슈 - 24시간 내 3건 (ZA 2건, ZB 1건)
        insertArticle("hot-a1", HOT_ISSUE_ID, COUNTRY_A, 1.0, now.minusHours(1), false);
        insertArticle("hot-a2", HOT_ISSUE_ID, COUNTRY_A, 3.0, now.minusHours(5), false);
        insertArticle("hot-b1", HOT_ISSUE_ID, COUNTRY_B, -2.0, now.minusHours(2), false);
        // 집계에서 빠져야 하는 기사
        insertArticle("hot-deleted", HOT_ISSUE_ID, COUNTRY_A, 9.0, now.minusHours(3), true);
        insertArticle("no-issue", null, COUNTRY_A, 9.0, now.minusHours(3), false);

        // 잔잔한이슈 - 24시간 내 2건
        insertArticle("minor-1", MINOR_ISSUE_ID, COUNTRY_A, 0.5, now.minusHours(4), false);
        insertArticle("minor-2", MINOR_ISSUE_ID, COUNTRY_B, 0.5, now.minusHours(6), false);

        // 지난이슈 - 24시간 밖 2건
        insertArticle("old-1", OLD_ISSUE_ID, COUNTRY_A, 5.0, now.minusHours(30), false);
        insertArticle("old-2", OLD_ISSUE_ID, COUNTRY_A, 5.0, now.minusHours(40), false);
    }

    private void insertCountry(String code, String nameKo, String nameEn, double latitude, double longitude) {
        jdbcTemplate.update(
                "INSERT INTO country (country_code, name_ko, name_en, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
                code, nameKo, nameEn, latitude, longitude);
    }

    private void insertIssue(long id, String name, LocalDateTime firstSeenAt) {
        jdbcTemplate.update("INSERT INTO issue (id, theme_id, name, first_seen_at) VALUES (?, ?, ?, ?)",
                id, THEME_ID, name, Timestamp.valueOf(firstSeenAt));
    }

    private void insertArticle(String id, Long issueId, String countryCode,
                               double toneScore, LocalDateTime publishedAt, boolean deleted) {
        jdbcTemplate.update("""
                        INSERT INTO article (
                            id, publisher_country_code, theme_id, issue_id, publisher, url, original_title,
                            crawled_at, theme_relevance_score, issue_similarity, tone_score,
                            created_at, published_at, issue_assigned_at, deleted_at
                        ) VALUES (?, ?, ?, ?, 'publisher', ?, 'title', ?, 1, 1, ?, ?, ?, ?, ?)
                        """,
                id, countryCode, THEME_ID, issueId, "https://example.com/" + id,
                Timestamp.valueOf(publishedAt), toneScore,
                Timestamp.valueOf(publishedAt), Timestamp.valueOf(publishedAt),
                Timestamp.valueOf(publishedAt),
                deleted ? Timestamp.valueOf(publishedAt) : null
        );
    }
}
