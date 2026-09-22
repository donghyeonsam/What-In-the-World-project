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
import java.time.*;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class DbWriterService {

    private static final String ARTICLE_UPSERT = "ARTICLE_UPSERT";
    private static final String ARTICLE_ISSUE_ASSIGNED = "ARTICLE_ISSUE_ASSIGNED";
    private static final String ISSUE_CREATE = "ISSUE_CREATE";
    private static final String ISSUE_UPSERT = """
            INSERT INTO issue
                (theme_id, name, embedding, first_seen_at, created_at, updated_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE
            SET first_seen_at = LEAST(issue.first_seen_at, EXCLUDED.first_seen_at),
                updated_at = GREATEST(issue.updated_at, EXCLUDED.updated_at),
                last_active_at = GREATEST(issue.last_active_at, EXCLUDED.last_active_at)
            RETURNING id
            """;
    private static final String ISSUE_LAST_ACTIVE_UPDATE = """
            UPDATE issue
            SET last_active_at = GREATEST(last_active_at, ?)
            WHERE id = ?
            """;

    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

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
            created.setCreatedAt(LocalDateTime.now(KST));
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
        String translatedTitle = payload.translatedTitle();
        article.setTranslatedTitle(
            translatedTitle == null || translatedTitle.isBlank()
                ? null
                : translatedTitle.trim()
        );
        // 요약은 없어도 기사를 저장한다. 필수로 막으면 요약 실패 기사가 통째로 버려진다.
        String summary = payload.summary();
        article.setSummary(
            summary == null || summary.isBlank()
                ? null
                : summary.trim()
        );
        // 요약 임베딩도 같은 이유로 필수가 아니다. 요약이 없으면 임베딩도 없다.
        // TEXT 컬럼이므로 JSON 배열 문자열로 직렬화해서 넣는다(Theme/Issue 와 동일).
        List<BigDecimal> summaryEmbedding = payload.summaryEmbedding();
        article.setSummaryEmbedding(
            summaryEmbedding == null || summaryEmbedding.isEmpty()
                ? null
                : writeJson(summaryEmbedding)
        );
        article.setOriginalTitle(requireText(payload.originalTitle(), "payload.original_title"));
        article.setCrawledAt(toKstLocalDateTime(require(payload.crawledAt(), "payload.crawled_at")));
        article.setToneScore(requireRange(
                payload.toneScore(), "payload.tone_score", BigDecimal.ZERO, BigDecimal.valueOf(100)
        ));
        article.setPublishedAt(toKstLocalDateTime(require(payload.publishedAt(), "payload.published_at")));

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
        LocalDateTime assignedAt = toKstLocalDateTime(occurredAt);
        article.setIssueAssignedAt(assignedAt);
        articleRepository.save(article);
        jdbcTemplate.update(ISSUE_LAST_ACTIVE_UPDATE, assignedAt, issue.getId());
    }

    private void createIssue(
            IssueCreatePayload payload,
            OffsetDateTime occurredAt
    ) {
        require(payload, "payload");
        List<String> articleIds = distinctArticleIds(payload.articleIds());
        Map<String, BigDecimal> articleSimilarities = issueSimilarities(
                payload.articleSimilarities(), articleIds
        );
        Theme theme = findTheme(require(payload.themeId(), "payload.theme_id"));
        String name = requireText(payload.name(), "payload.name");
        if (name.length() > 50) {
            throw new IllegalArgumentException("payload.name exceeds 50 characters");
        }
        String embedding = writeJson(requireNonEmpty(payload.embedding(), "payload.embedding"));
        LocalDateTime firstSeenAt = toKstLocalDateTime(
                require(payload.firstSeenAt(), "payload.first_seen_at")
        );
        LocalDateTime eventTime = toKstLocalDateTime(occurredAt);
        Long issueId = jdbcTemplate.queryForObject(
                ISSUE_UPSERT,
                Long.class,
                theme.getId(), name, embedding, firstSeenAt, eventTime, eventTime, eventTime
        );
        if (issueId == null) {
            throw new IllegalStateException("Issue upsert did not return an id");
        }
        Issue issue = findIssue(issueId);

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

        LocalDateTime assignedAt = toKstLocalDateTime(occurredAt);
        for (Article article : articles) {
            article.setIssue(issue);
            article.setIssueSimilarity(articleSimilarities.get(article.getId()));
            article.setIssueAssignedAt(assignedAt);
        }
        articleRepository.saveAll(articles);
    }

    private Map<String, BigDecimal> issueSimilarities(
            Map<String, BigDecimal> values,
            List<String> articleIds
    ) {
        // 배포 전에 발행된 ISSUE_CREATE 이벤트도 재처리할 수 있도록 필드가 없는
        // 구계약은 허용한다. 새 계약에서 필드가 있다면 일부 기사만 누락되는 것을
        // 막기 위해 article_ids와 정확히 같은 키 집합을 요구한다.
        if (values == null) {
            return Map.of();
        }

        Map<String, BigDecimal> normalized = new LinkedHashMap<>();
        for (Map.Entry<String, BigDecimal> entry : values.entrySet()) {
            String articleId = requireText(
                    entry.getKey(), "payload.article_similarities key"
            );
            BigDecimal similarity = requireRange(
                    entry.getValue(),
                    "payload.article_similarities[" + articleId + "]",
                    BigDecimal.ONE.negate(),
                    BigDecimal.ONE
            );
            if (normalized.put(articleId, similarity) != null) {
                throw new IllegalArgumentException(
                        "payload.article_similarities contains duplicate article_id: "
                                + articleId
                );
            }
        }

        Set<String> expectedIds = new LinkedHashSet<>(articleIds);
        if (!normalized.keySet().equals(expectedIds)) {
            throw new IllegalArgumentException(
                    "payload.article_similarities keys must match payload.article_ids"
            );
        }
        return Map.copyOf(normalized);
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

    private static LocalDateTime toKstLocalDateTime(OffsetDateTime value) {
        return value.atZoneSameInstant(KST).toLocalDateTime();
    }
}
