package com.ssafy.witw.analysis.repository;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.*;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisPromptService.PreparedPrompt;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import com.ssafy.witw.support.RepositoryTest;
import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

// TestContainerSupport supplies an isolated test DB. No GMS or scheduled execution is enabled here.
@RepositoryTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@Import({IssueCountryAnalysisArticleRepository.class, IssueCountryAnalysisResultRepository.class,
        IssueCountryAnalysisArticleService.class, IssueCountryAnalysisPromptService.class,
        IssueCountryAnalysisResponseValidator.class, IssueCountryAnalysisResultService.class,
        IssueCountryAnalysisWorkerService.class, IssueCountryAnalysisPersistenceTest.JsonConfig.class})
class IssueCountryAnalysisPersistenceTest extends TestContainerSupport {
    private static final long ID = 949_001;
    private static final LocalDateTime END = LocalDateTime.of(2026, 9, 18, 14, 0);
    private static final LocalDateTime START = END.minusHours(24);
    private static final Target TARGET = new Target(ID, "분석 이슈", "ZQ", "테스트 국가", 15);
    private static final AnalysisResult RESULT = new AnalysisResult("제목", "요약", List.of("관점 \"인용\"", "다른 관점"));

    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;
    @Autowired IssueCountryAnalysisWorkerService worker;
    @Autowired IssueCountryAnalysisResultService results;
    @MockitoBean IssueCountryAnalysisGmsService gms;

    @TestConfiguration(proxyBeanMethods = false)
    static class JsonConfig {
        @Bean ObjectMapper analysisTestMapper() { return JsonMapper.builder().build(); }
    }

    @BeforeEach
    void seed_test_database() {
        jdbc.update("INSERT INTO country (country_code, name_ko, name_en) VALUES ('ZQ', '테스트 국가', 'Test country')");
        jdbc.update("INSERT INTO field (id, code, name, description) VALUES (?, 'PERSISTENCE_TEST', '분야', '분야')", ID);
        jdbc.update("INSERT INTO theme (id, field_id, code, name, description) VALUES (?, ?, 'PERSISTENCE_TEST', '테마', '테마')", ID, ID);
        jdbc.update("INSERT INTO issue (id, theme_id, name, created_at) VALUES (?, ?, '분석 이슈', ?)", ID, ID, Timestamp.valueOf(START));
        for (int i = 0; i < 15; i++) {
            jdbc.update("""
                    INSERT INTO article (id, publisher_country_code, theme_id, issue_id, publisher, url,
                        original_title, summary, crawled_at, theme_relevance_score, issue_similarity,
                        tone_score, created_at, published_at, issue_assigned_at)
                    VALUES (?, 'ZQ', ?, ?, 'test publisher', ?, ?, '기사 요약', ?, 1, 1, 50, ?, ?, ?)
                    """, "persistence-" + i, ID, ID, "https://example.invalid/" + i, "제목 " + i,
                    Timestamp.valueOf(START), Timestamp.valueOf(START), Timestamp.valueOf(START.plusMinutes(i)), Timestamp.valueOf(START));
        }
    }

    @AfterEach
    void remove_only_test_fixtures() {
        jdbc.update("DELETE FROM issue_country_analysis WHERE issue_id = ?", ID);
        jdbc.update("DELETE FROM article WHERE issue_id = ?", ID);
        jdbc.update("DELETE FROM issue WHERE id = ?", ID);
        jdbc.update("DELETE FROM theme WHERE id = ?", ID);
        jdbc.update("DELETE FROM field WHERE id = ?", ID);
        jdbc.update("DELETE FROM country WHERE country_code = 'ZQ'");
    }

    @Test
    void worker_persists_the_validated_result_and_every_input_representative() {
        when(gms.analyze(any())).thenReturn(mapper.writeValueAsString(RESULT));
        worker.analyze(TARGET, START, END);
        ArgumentCaptor<PreparedPrompt> prompt = ArgumentCaptor.forClass(PreparedPrompt.class);
        verify(gms).analyze(prompt.capture());
        var row = jdbc.queryForMap("SELECT * FROM issue_country_analysis WHERE issue_id = ?", ID);
        long analysisId = ((Number) row.get("id")).longValue();
        assertThat(row.get("country_code")).isEqualTo("ZQ");
        assertThat(row.get("title")).isEqualTo(RESULT.title());
        assertThat(row.get("summary")).isEqualTo(RESULT.summary());
        assertThat(((Number) row.get("article_count")).longValue()).isEqualTo(15);
        assertThat(((Timestamp) row.get("created_at")).toLocalDateTime()).isEqualTo(END);
        assertThat(mapper.readValue(row.get("details").toString(), List.class)).isEqualTo(RESULT.details());
        assertThat(jdbc.queryForList("SELECT article_id FROM issue_country_analysis_evidence WHERE analysis_id = ?", String.class, analysisId))
                .hasSize(12).containsExactlyInAnyOrderElementsOf(prompt.getValue().representativeArticleIds());
    }

    @Test
    void invalid_evidence_fk_rolls_back_parent_and_preceding_evidence_rows() {
        assertThatThrownBy(() -> results.save(TARGET, END, RESULT, List.of("persistence-0", "missing-article")))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM issue_country_analysis WHERE issue_id = ?", Long.class, ID)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM issue_country_analysis_evidence WHERE article_id = 'persistence-0'", Long.class)).isZero();
    }

    @Test
    void repeated_window_does_not_overwrite_or_duplicate_an_existing_analysis() {
        long id = results.save(TARGET, END, RESULT, List.of("persistence-0", "persistence-0", "persistence-1"));
        assertThatThrownBy(() -> results.save(TARGET, END, RESULT, List.of("persistence-2")))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM issue_country_analysis WHERE issue_id = ?", Long.class, ID)).isEqualTo(1);
        assertThat(jdbc.queryForList("SELECT article_id FROM issue_country_analysis_evidence WHERE analysis_id = ?", String.class, id))
                .containsExactlyInAnyOrder("persistence-0", "persistence-1");
    }
}
