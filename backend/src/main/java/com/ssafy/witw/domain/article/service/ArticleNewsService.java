package com.ssafy.witw.domain.article.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.NewsArticleQueryRepository;
import com.ssafy.witw.domain.article.dto.ArticleDetailResponse;
import com.ssafy.witw.domain.article.dto.ArticleFiltersResponse;
import com.ssafy.witw.domain.article.dto.ArticleListItem;
import com.ssafy.witw.domain.article.dto.ArticlePageResponse;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.field.dao.FieldRepository;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ArticleNewsService {
    private final NewsArticleQueryRepository queryRepository;
    private final CountryRepository countryRepository;
    private final FieldRepository fieldRepository;
    private final ThemeRepository themeRepository;

    public ArticleFiltersResponse getFilters() {
        List<ArticleFiltersResponse.CountryOption> countries = queryRepository.findPublisherCountries()
                .stream()
                .map(country -> new ArticleFiltersResponse.CountryOption(
                        country.getCountryCode(), country.getNameKo()))
                .toList();

        Map<Long, List<ArticleFiltersResponse.ThemeOption>> themesByField = themeRepository.findAll()
                .stream()
                .collect(Collectors.groupingBy(
                        theme -> theme.getField().getId(),
                        Collectors.mapping(theme -> new ArticleFiltersResponse.ThemeOption(
                                theme.getId(), theme.getName()), Collectors.toList())));
        List<ArticleFiltersResponse.FieldOption> fields = fieldRepository.findAll().stream()
                .sorted(Comparator.comparing(field -> field.getId()))
                .map(field -> new ArticleFiltersResponse.FieldOption(
                        field.getId(), field.getName(),
                        themesByField.getOrDefault(field.getId(), List.of()).stream()
                                .sorted(Comparator.comparing(ArticleFiltersResponse.ThemeOption::themeId))
                                .toList()))
                .toList();
        return new ArticleFiltersResponse(countries, fields);
    }

    public ArticlePageResponse getArticles(String countryCode, Long fieldId, Long themeId,
                                           LocalDate from, LocalDate to, int page, int size) {
        if (page < 1 || size < 1 || size > 100
                || ((long) page - 1L) * size > Integer.MAX_VALUE
                || (fieldId != null && fieldId < 1)
                || (themeId != null && themeId < 1)
                || (from != null && to != null && from.isAfter(to))
                || (to != null && to.equals(LocalDate.MAX))) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }

        String normalizedCountry = countryCode == null ? null : countryCode.toUpperCase(Locale.ROOT);
        if (normalizedCountry != null
                && (!normalizedCountry.matches("[A-Z]{2}") || !countryRepository.existsById(normalizedCountry))) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
        if (fieldId != null && !fieldRepository.existsById(fieldId)) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
        if (themeId != null) {
            var theme = themeRepository.findById(themeId)
                    .orElseThrow(() -> new GlobalException(ErrorCode.INVALID_INPUT_VALUE));
            if (fieldId != null && !theme.getField().getId().equals(fieldId)) {
                throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
            }
        }

        LocalDateTime fromInclusive = from == null ? null : from.atStartOfDay();
        LocalDateTime toExclusive = to == null ? null : to.plusDays(1).atStartOfDay();
        var result = queryRepository.search(normalizedCountry, fieldId, themeId,
                fromInclusive, toExclusive, page, size);
        long totalPages = result.totalElements() / size
                + (result.totalElements() % size == 0 ? 0 : 1);
        return new ArticlePageResponse(result.items().stream().map(ArticleListItem::from).toList(),
                page, size, result.totalElements(), totalPages);
    }

    public ArticleDetailResponse getArticle(String articleId) {
        if (articleId == null || articleId.isBlank()) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
        return queryRepository.findVisibleById(articleId)
                .map(ArticleDetailResponse::from)
                .orElseThrow(() -> new GlobalException(ErrorCode.ENTITY_NOT_FOUND));
    }
}
