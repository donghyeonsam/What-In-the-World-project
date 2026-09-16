package com.ssafy.witw.domain.article.dao;

import com.ssafy.witw.domain.article.entity.Article;
import com.ssafy.witw.domain.country.entity.Country;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/** Read-only queries kept separate from the existing ArticleRepository. */
@Repository
@RequiredArgsConstructor
public class NewsArticleQueryRepository {
    private final EntityManager entityManager;

    public record SearchResult(List<Article> items, long totalElements) {
    }

    public SearchResult search(String countryCode, Long fieldId, Long themeId,
                               LocalDateTime fromInclusive, LocalDateTime toExclusive,
                               int page, int size) {
        String where = " where a.deletedAt is null"
                + (countryCode == null ? "" : " and c.countryCode = :countryCode")
                + (fieldId == null ? "" : " and f.id = :fieldId")
                + (themeId == null ? "" : " and t.id = :themeId")
                + (fromInclusive == null ? "" : " and a.publishedAt >= :fromInclusive")
                + (toExclusive == null ? "" : " and a.publishedAt < :toExclusive");

        String joins = " from Article a join a.publisherCountryCode c"
                + " join a.theme t join t.field f";
        TypedQuery<Long> countQuery = entityManager.createQuery(
                "select count(a)" + joins + where, Long.class);
        bind(countQuery, countryCode, fieldId, themeId, fromInclusive, toExclusive);
        long total = countQuery.getSingleResult();
        long offset = ((long) page - 1L) * size;
        if (offset >= total) {
            return new SearchResult(List.of(), total);
        }

        String fetchJoins = " from Article a join fetch a.publisherCountryCode c"
                + " join fetch a.theme t join fetch t.field f";
        TypedQuery<Article> listQuery = entityManager.createQuery(
                "select a" + fetchJoins + where + " order by a.publishedAt desc, a.id desc",
                Article.class);
        bind(listQuery, countryCode, fieldId, themeId, fromInclusive, toExclusive);
        return new SearchResult(listQuery.setFirstResult((int) offset).setMaxResults(size).getResultList(), total);
    }

    public Optional<Article> findVisibleById(String articleId) {
        return entityManager.createQuery("""
                select a from Article a
                join fetch a.publisherCountryCode
                join fetch a.theme t
                join fetch t.field
                where a.id = :articleId and a.deletedAt is null
                """, Article.class)
                .setParameter("articleId", articleId)
                .getResultStream()
                .findFirst();
    }

    public List<Country> findPublisherCountries() {
        return entityManager.createQuery("""
                select distinct c from Article a
                join a.publisherCountryCode c
                where a.deletedAt is null
                order by c.nameKo, c.countryCode
                """, Country.class).getResultList();
    }

    private static void bind(TypedQuery<?> query, String countryCode, Long fieldId, Long themeId,
                             LocalDateTime fromInclusive, LocalDateTime toExclusive) {
        if (countryCode != null) query.setParameter("countryCode", countryCode);
        if (fieldId != null) query.setParameter("fieldId", fieldId);
        if (themeId != null) query.setParameter("themeId", themeId);
        if (fromInclusive != null) query.setParameter("fromInclusive", fromInclusive);
        if (toExclusive != null) query.setParameter("toExclusive", toExclusive);
    }
}
