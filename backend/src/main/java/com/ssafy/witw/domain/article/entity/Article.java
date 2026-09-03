package com.ssafy.witw.domain.article.entity;

import com.ssafy.witw.domain.country.entity.Country;
import com.ssafy.witw.domain.issue.entity.Issue;
import com.ssafy.witw.domain.theme.entity.Theme;
import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Getter
@Setter
@Entity
@Table(name = "article")
public class Article {
    @Id
    @Column(name = "id", nullable = false)
    private String id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "publisher_country_code", nullable = false)
    private Country publisherCountryCode;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "theme_id", nullable = false)
    private Theme theme;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "issue_id")
    private Issue issue;

    @Size(max = 255)
    @NotNull
    @Column(name = "publisher", nullable = false)
    private String publisher;

    @Size(max = 1000)
    @NotNull
    @Column(name = "url", nullable = false, length = 1000)
    private String url;

    @NotNull
    @Column(name = "original_title", nullable = false, length = Integer.MAX_VALUE)
    private String originalTitle;

    @Column(name = "translated_title", length = Integer.MAX_VALUE)
    private String translatedTitle;

    @NotNull
    @Column(name = "crawled_at", nullable = false)
    private Instant crawledAt;

    @NotNull
    @Column(name = "theme_relevance_score", nullable = false)
    private BigDecimal themeRelevanceScore;

    @Column(name = "embedding", length = Integer.MAX_VALUE)
    private String embedding;

    @NotNull
    @Column(name = "issue_similarity", nullable = false)
    private BigDecimal issueSimilarity;

    @NotNull
    @Column(name = "tone_score", nullable = false)
    private BigDecimal toneScore;

    @Column(name = "summary", length = Integer.MAX_VALUE)
    private String summary;

    @NotNull
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @NotNull
    @Column(name = "published_at", nullable = false)
    private Instant publishedAt;

    @NotNull
    @Column(name = "issue_assigned_at", nullable = false)
    private Instant issueAssignedAt;

    @Column(name = "deleted_at")
    private Instant deletedAt;

}