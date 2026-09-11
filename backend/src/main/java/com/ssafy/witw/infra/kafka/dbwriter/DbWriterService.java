package com.ssafy.witw.infra.kafka.dbwriter;

import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.entity.Article;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.country.entity.Country;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.entity.Issue;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.entity.Theme;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class DbWriterService {

    private static final String ARTICLE_UPSERT = "ARTICLE_UPSERT";
    private static final String ARTICLE_ISSUE_ASSIGNED = "ARTICLE_ISSUE_ASSIGNED";
    private static final String ISSUE_CREATE = "ISSUE_CREATE";

    private final ObjectMapper objectMapper;
    private final ArticleRepository articleRepository;
    private final CountryRepository countryRepository;
    private final ThemeRepository themeRepository;
    private final IssueRepository issueRepository;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void handle(DbWriterEvent event) {
        require(event, "event");
        requireText(event.eventType(), "event_type");
        require(event.occurredAt(), "occurred_at");
        require(event.payload(), "payload");

        switch (event.eventType()) {
            case ARTICLE_UPSERT -> upsertArticle(convert(event, ArticleUpsertPayload.class));
            case ARTICLE_ISSUE_ASSIGNED -> assignArticleToIssue(
                    convert(event, ArticleIssueAssignedPayload.class), event.occurredAt()
            );
            case ISSUE_CREATE -> createIssue(
                    convert(event, IssueCreatePayload.class), event.occurredAt()
            );
            default -> throw new IllegalArgumentException(
                    "Unsupported DB Writer event_type: " + event.eventType()
            );
        }
    }

    private void upsertArticle(ArticleUpsertPayload payload) {
        require(payload, "payload");
        String articleId = requireText(payload.articleId(), "payload.article_id");
        String publisherCountryCode = requireCountryCode(
                payload.publisherCountryCode(), "payload.publisher_country_code"
        );
        Country publisherCountry = findCountry(publisherCountryCode);
        Theme theme = findTheme(require(payload.themeId(), "payload.theme_id"));

        Article article = articleRepository.findById(articleId).orElseGet(() -> {
            Article created = new Article();
            created.setId(articleId);
            created.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
            return created;
        });

        article.setPublisherCountryCode(publisherCountry);
        article.setTheme(theme);
        article.setThemeRelevanceScore(requireRange(
                payload.themeRelevanceScore(),
                "payload.theme_relevance_score",
                BigDecimal.ONE.negate(),
                BigDecimal.ONE
        ));
        article.setPublisher(requireMaxLength(
                payload.publisher(), "payload.publisher", 255
        ));
        article.setUrl(requireMaxLength(payload.url(), "payload.url", 1000));
        article.setOriginalTitle(requireText(payload.originalTitle(), "payload.original_title"));
        article.setCrawledAt(toUtcLocalDateTime(require(payload.crawledAt(), "payload.crawled_at")));
        article.setToneScore(requireRange(
                payload.toneScore(), "payload.tone_score", BigDecimal.ZERO, BigDecimal.valueOf(100)
        ));
        article.setPublishedAt(toUtcLocalDateTime(require(payload.publishedAt(), "payload.published_at")));

        articleRepository.saveAndFlush(article);
        replaceCountryMentions(articleId, payload.mentionedCountries());
    }

    private void replaceCountryMentions(
            String articleId,
            List<MentionedCountryPayload> mentionedCountries
    ) {
        jdbcTemplate.update(
                "DELETE FROM article_country_mention WHERE article_id = ?",
                articleId
        );

        if (mentionedCountries == null || mentionedCountries.isEmpty()) {
            return;
        }

        Set<String> countryCodes = new LinkedHashSet<>();
        for (MentionedCountryPayload mention : mentionedCountries) {
            require(mention, "payload.mentioned_countries[]");
            Integer count = require(
                    mention.count(), "payload.mentioned_countries[].count"
            );
            if (count < 0) {
                throw new IllegalArgumentException(
                        "payload.mentioned_countries[].count must be non-negative"
                );
            }
            String countryCode = requireCountryCode(
                    mention.countryCode(), "payload.mentioned_countries[].country_code"
            );
            findCountry(countryCode);
            countryCodes.add(countryCode);
        }

        for (String countryCode : countryCodes) {
            jdbcTemplate.update(
                    "INSERT INTO article_country_mention (article_id, country_code) VALUES (?, ?)",
                    articleId,
                    countryCode
            );
        }
    }

    private void assignArticleToIssue(
            ArticleIssueAssignedPayload payload,
            OffsetDateTime occurredAt
    ) {
        require(payload, "payload");
        Article article = findArticle(requireText(payload.articleId(), "payload.article_id"));
        Issue issue = findIssue(require(payload.issueId(), "payload.issue_id"));
        article.setIssue(issue);
        article.setIssueSimilarity(requireRange(
                payload.similarity(), "payload.similarity", BigDecimal.ZERO, BigDecimal.ONE
        ));
        article.setIssueAssignedAt(toUtcLocalDateTime(occurredAt));
        articleRepository.save(article);
    }

    private void createIssue(
            IssueCreatePayload payload,
            OffsetDateTime occurredAt
    ) {
        require(payload, "payload");
        List<String> articleIds = distinctArticleIds(payload.articleIds());
        Issue issue = new Issue();
        issue.setTheme(findTheme(require(payload.themeId(), "payload.theme_id")));
        String name = requireText(payload.name(), "payload.name");
        if (name.length() > 50) {
            throw new IllegalArgumentException("payload.name exceeds 50 characters");
        }
        issue.setName(name);
        issue.setEmbedding(writeJson(requireNonEmpty(payload.embedding(), "payload.embedding")));
        issue.setFirstSeenAt(toUtcLocalDateTime(
                require(payload.firstSeenAt(), "payload.first_seen_at")
        ));
        LocalDateTime eventTime = toUtcLocalDateTime(occurredAt);
        issue.setCreatedAt(eventTime);
        issue.setUpdatedAt(eventTime);
        issue = issueRepository.saveAndFlush(issue);

        List<Article> articles = articleRepository.findAllById(articleIds);
        if (articles.size() != articleIds.size()) {
            Set<String> foundIds = new LinkedHashSet<>();
            articles.forEach(article -> foundIds.add(article.getId()));
            List<String> missingIds = articleIds.stream()
                    .filter(articleId -> !foundIds.contains(articleId))
                    .toList();
            throw new IllegalStateException(
                    "ISSUE_CREATE references articles not stored yet: " + missingIds
            );
        }

        LocalDateTime assignedAt = toUtcLocalDateTime(occurredAt);
        for (Article article : articles) {
            article.setIssue(issue);
            article.setIssueSimilarity(null);
            article.setIssueAssignedAt(assignedAt);
        }
        articleRepository.saveAll(articles);
    }

    private List<String> distinctArticleIds(List<String> articleIds) {
        requireNonEmpty(articleIds, "payload.article_ids");
        LinkedHashSet<String> distinctIds = new LinkedHashSet<>();
        articleIds.forEach(articleId -> distinctIds.add(
                requireText(articleId, "payload.article_ids[]")
        ));
        return List.copyOf(distinctIds);
    }

    private Country findCountry(String countryCode) {
        return countryRepository.findById(countryCode)
                .orElseThrow(() -> new IllegalStateException(
                        "Country not found: " + countryCode
                ));
    }

    private Theme findTheme(Long themeId) {
        return themeRepository.findById(themeId)
                .orElseThrow(() -> new IllegalStateException("Theme not found: " + themeId));
    }

    private Article findArticle(String articleId) {
        return articleRepository.findById(articleId)
                .orElseThrow(() -> new IllegalStateException("Article not found: " + articleId));
    }

    private Issue findIssue(Long issueId) {
        return issueRepository.findById(issueId)
                .orElseThrow(() -> new IllegalStateException("Issue not found: " + issueId));
    }

    private <T> T convert(DbWriterEvent event, Class<T> payloadType) {
        try {
            return objectMapper.treeToValue(event.payload(), payloadType);
        } catch (JacksonException exception) {
            throw new IllegalArgumentException(
                    "Invalid payload for " + event.eventType(), exception
            );
        }
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JacksonException exception) {
            throw new IllegalArgumentException("Unable to serialize embedding", exception);
        }
    }

    private static String requireCountryCode(String value, String field) {
        String countryCode = requireText(value, field).toUpperCase();
        if (!countryCode.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException(field + " must be an ISO alpha-2 country code");
        }
        return countryCode;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must be a non-empty string");
        }
        return value.trim();
    }

    private static String requireMaxLength(String value, String field, int maxLength) {
        String text = requireText(value, field);
        if (text.length() > maxLength) {
            throw new IllegalArgumentException(field + " exceeds " + maxLength + " characters");
        }
        return text;
    }

    private static BigDecimal requireRange(
            BigDecimal value,
            String field,
            BigDecimal minimum,
            BigDecimal maximum
    ) {
        require(value, field);
        if (value.compareTo(minimum) < 0 || value.compareTo(maximum) > 0) {
            throw new IllegalArgumentException(
                    field + " must be between " + minimum + " and " + maximum
            );
        }
        return value;
    }

    private static <T> T require(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }

    private static <T> List<T> requireNonEmpty(List<T> value, String field) {
        require(value, field);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be empty");
        }
        return value;
    }

    private static LocalDateTime toUtcLocalDateTime(OffsetDateTime value) {
        return value.withOffsetSameInstant(ZoneOffset.UTC).toLocalDateTime();
    }
}
