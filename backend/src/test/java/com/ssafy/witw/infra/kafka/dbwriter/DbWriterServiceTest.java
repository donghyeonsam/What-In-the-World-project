package com.ssafy.witw.infra.kafka.dbwriter;

import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.entity.Article;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.country.entity.Country;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.entity.Issue;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.entity.Theme;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DbWriterServiceTest {

    private final ObjectMapper objectMapper = JsonMapper.builder()
            .findAndAddModules()
            .build();

    @Mock
    private ArticleRepository articleRepository;
    @Mock
    private CountryRepository countryRepository;
    @Mock
    private ThemeRepository themeRepository;
    @Mock
    private IssueRepository issueRepository;
    @Mock
    private JdbcTemplate jdbcTemplate;

    private DbWriterService dbWriterService;

    @BeforeEach
    void setUp() {
        dbWriterService = new DbWriterService(
                objectMapper,
                articleRepository,
                countryRepository,
                themeRepository,
                issueRepository,
                jdbcTemplate
        );
    }

    @Test
    void articleUpsertStoresArticleAndReplacesCountryMentions() throws Exception {
        Country korea = country("KR");
        Country us = country("US");
        Theme theme = theme(27L);
        when(countryRepository.findById("KR")).thenReturn(Optional.of(korea));
        when(countryRepository.findById("US")).thenReturn(Optional.of(us));
        when(themeRepository.findById(27L)).thenReturn(Optional.of(theme));
        when(articleRepository.findById("a-123")).thenReturn(Optional.empty());

        DbWriterEvent event = objectMapper.readValue("""
                {
                  "event_type": "ARTICLE_UPSERT",
                  "occurred_at": "2026-09-04T03:20:15+09:00",
                  "payload": {
                    "article_id": "a-123",
                    "publisher_country_code": "KR",
                    "theme_id": 27,
                    "theme_relevance_score": 0.8123,
                    "publisher": "Publisher",
                    "url": "https://example.com/article",
                    "original_title": "Title",
                    "crawled_at": "2026-09-01T08:22:28.256121Z",
                    "embedding": [0.031, -0.114],
                    "tone_score": 51.5,
                    "published_at": "2026-09-01T08:15:03Z",
                    "mentioned_countries": [
                      {"country_code": "US", "count": 3},
                      {"country_code": "US", "count": 1}
                    ]
                  }
                }
                """, DbWriterEvent.class);

        dbWriterService.handle(event);

        ArgumentCaptor<Article> captor = ArgumentCaptor.forClass(Article.class);
        verify(articleRepository).saveAndFlush(captor.capture());
        Article saved = captor.getValue();
        assertThat(saved.getId()).isEqualTo("a-123");
        assertThat(saved.getPublisherCountryCode()).isSameAs(korea);
        assertThat(saved.getTheme()).isSameAs(theme);
        assertThat(saved.getThemeRelevanceScore()).isEqualByComparingTo("0.8123");
        assertThat(saved.getEmbedding()).isEqualTo("[0.031,-0.114]");
        assertThat(saved.getCrawledAt()).isEqualTo(
                LocalDateTime.parse("2026-09-01T08:22:28.256121")
        );
        verify(jdbcTemplate).update(
                "DELETE FROM article_country_mention WHERE article_id = ?",
                "a-123"
        );
        verify(jdbcTemplate).update(
                "INSERT INTO article_country_mention (article_id, country_code) VALUES (?, ?)",
                "a-123",
                "US"
        );
    }

    @Test
    void articleIssueAssignedUpdatesArticle() throws Exception {
        Article article = new Article();
        article.setId("a-123");
        Issue issue = new Issue();
        issue.setId(102L);
        when(articleRepository.findById("a-123")).thenReturn(Optional.of(article));
        when(issueRepository.findById(102L)).thenReturn(Optional.of(issue));

        DbWriterEvent event = objectMapper.readValue("""
                {
                  "event_type": "ARTICLE_ISSUE_ASSIGNED",
                  "occurred_at": "2026-09-03T06:40:02Z",
                  "payload": {
                    "article_id": "a-123",
                    "issue_id": 102,
                    "similarity": 0.94
                  }
                }
                """, DbWriterEvent.class);

        dbWriterService.handle(event);

        assertThat(article.getIssue()).isSameAs(issue);
        assertThat(article.getIssueSimilarity()).isEqualByComparingTo("0.94");
        assertThat(article.getIssueAssignedAt()).isEqualTo(
                LocalDateTime.parse("2026-09-03T06:40:02")
        );
        verify(articleRepository).save(article);
    }

    @Test
    void articleUpsertRejectsMissingThemeRelevanceScore() throws Exception {
        Country korea = country("KR");
        Theme theme = theme(27L);
        when(countryRepository.findById("KR")).thenReturn(Optional.of(korea));
        when(themeRepository.findById(27L)).thenReturn(Optional.of(theme));
        when(articleRepository.findById("a-123")).thenReturn(Optional.empty());

        DbWriterEvent event = objectMapper.readValue("""
                {
                  "event_type": "ARTICLE_UPSERT",
                  "occurred_at": "2026-09-04T03:20:15Z",
                  "payload": {
                    "article_id": "a-123",
                    "publisher_country_code": "KR",
                    "theme_id": 27,
                    "publisher": "Publisher",
                    "url": "https://example.com/article",
                    "original_title": "Title",
                    "crawled_at": "2026-09-01T08:22:28Z",
                    "embedding": [0.031],
                    "tone_score": 51.5,
                    "published_at": "2026-09-01T08:15:03Z",
                    "mentioned_countries": []
                  }
                }
                """, DbWriterEvent.class);

        assertThatThrownBy(() -> dbWriterService.handle(event))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("payload.theme_relevance_score");
    }

    @Test
    void issueCreateStoresIssueAndAssignsArticles() throws Exception {
        Theme theme = theme(12L);
        Article firstArticle = article("a-101");
        Article secondArticle = article("a-102");
        when(themeRepository.findById(12L)).thenReturn(Optional.of(theme));
        when(issueRepository.saveAndFlush(any(Issue.class))).thenAnswer(invocation -> {
            Issue saved = invocation.getArgument(0);
            saved.setId(205L);
            return saved;
        });
        when(articleRepository.findAllById(List.of("a-101", "a-102")))
                .thenReturn(List.of(firstArticle, secondArticle));

        DbWriterEvent event = objectMapper.readValue("""
                {
                  "event_type": "ISSUE_CREATE",
                  "occurred_at": "2026-09-03T06:50:00Z",
                  "payload": {
                    "theme_id": 12,
                    "name": "New issue",
                    "embedding": [0.031, -0.114],
                    "article_ids": ["a-101", "a-102"],
                    "first_seen_at": "2026-09-03T03:35:24Z"
                  }
                }
                """, DbWriterEvent.class);

        dbWriterService.handle(event);

        ArgumentCaptor<Issue> issueCaptor = ArgumentCaptor.forClass(Issue.class);
        verify(issueRepository).saveAndFlush(issueCaptor.capture());
        assertThat(issueCaptor.getValue().getName()).isEqualTo("New issue");
        assertThat(firstArticle.getIssue()).isSameAs(issueCaptor.getValue());
        assertThat(secondArticle.getIssue()).isSameAs(issueCaptor.getValue());
        verify(articleRepository).saveAll(List.of(firstArticle, secondArticle));
    }

    private static Country country(String code) {
        Country country = new Country();
        country.setCountryCode(code);
        return country;
    }

    private static Theme theme(long id) {
        Theme theme = new Theme();
        theme.setId(id);
        return theme;
    }

    private static Article article(String id) {
        Article article = new Article();
        article.setId(id);
        return article;
    }
}
