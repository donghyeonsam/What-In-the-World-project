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
import java.time.LocalDateTime;
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
    private LocalDateTime crawledAt;

    @NotNull
    @Column(name = "theme_relevance_score", nullable = false)
    private BigDecimal themeRelevanceScore;

    @Column(name = "issue_similarity")
    private BigDecimal issueSimilarity;

    @NotNull
    @Column(name = "tone_score", nullable = false)
    private BigDecimal toneScore;

    @Column(name = "summary", length = Integer.MAX_VALUE)
    private String summary;

    // 요약문의 E5 임베딩(768차원)을 JSON 배열 문자열로 보관한다.
    // theme.embedding / issue.embedding 과 동일한 TEXT 방식이다.
    @Column(name = "summary_embedding", length = Integer.MAX_VALUE)
    private String summaryEmbedding;

    @NotNull
    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @NotNull
    @Column(name = "published_at", nullable = false)
    private LocalDateTime publishedAt;

    @Column(name = "issue_assigned_at")
    private LocalDateTime issueAssignedAt;

    @Column(name = "deleted_at")
    private LocalDateTime deletedAt;

}
