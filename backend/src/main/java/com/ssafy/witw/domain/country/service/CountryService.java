package com.ssafy.witw.domain.country.service;

import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.dao.CountryRepository.MentionRatioRow;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.country.dto.CountryMainResponse.MentionRatio;
import com.ssafy.witw.domain.country.dto.CountryMainResponse;
import com.ssafy.witw.domain.country.entity.Country;
import com.ssafy.witw.domain.theme.dao.ThemeRepository.PopularThemeRow;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import com.ssafy.witw.domain.theme.dto.PopularTheme;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class CountryService {

    private static final int POPULAR_THEME_LIMIT = 3;   // FR-DSB-007: 3개
    private static final int MENTION_LIMIT = 4;   // FR-DSB-010: 최대 4개
    private static final int REPRESENT_ARTICLE_LIMIT = 3;

    private final CountryRepository countryRepository;
    private final CountryFinder countryFinder;
    private final ThemeRepository themeRepository;
    private final ArticleRepository articleRepository;

    // 진입점에서 국가를 한 번만 검증하고, 이후 조회는 리포지토리에서 바로 가져온다
    public CountryMainResponse getCountryMain(String countryCode) {
        return getCountryMain(countryCode, QueryTime.now());
    }

    public CountryMainResponse getCountryMain(String countryCode, LocalDateTime asOf) {
        Country country = countryFinder.getCountry(countryCode);

        return new CountryMainResponse(
                country.getCountryCode(),
                country.getNameKo(),
                articleRepository.countArticlesLast24Hours(countryCode, null, asOf),
                getGlobalRank(countryCode, asOf),
                getPopularThemes(countryCode, POPULAR_THEME_LIMIT, asOf),
                toMentionRatios(countryRepository.findOutgoingMentionRatios(countryCode, MENTION_LIMIT, asOf)),
                toMentionRatios(countryRepository.findIncomingMentionRatios(countryCode, MENTION_LIMIT, asOf)),
                getRepresentArticles(countryCode, REPRESENT_ARTICLE_LIMIT, asOf)
        );
    }

    // country LEFT JOIN이라 기사 0건인 국가도 공동 순위를 받고,
    // getCountry()로 존재를 이미 확인했으므로 항상 순위가 나온다.
    private int getGlobalRank(String countryCode, LocalDateTime asOf) {
        return articleRepository.getCountryRankByArticleCounts(countryCode, asOf);
    }

    private List<PopularTheme> getPopularThemes(String countryCode, int limit, LocalDateTime asOf) {
        return themeRepository.findPopularThemes(countryCode, limit, asOf)
                .stream()
                .map(this::toPopularTheme)
                .toList();
    }

    private PopularTheme toPopularTheme(PopularThemeRow row) {
        return new PopularTheme(
                row.getThemeId(),
                row.getFieldName(),
                row.getThemeName(),
                row.getArticleCount24()
        );
    }

    private List<RepresentArticle> getRepresentArticles(String countryCode, int limit, LocalDateTime asOf) {
        return articleRepository.findRepresentArticlesByCountry(countryCode, limit, asOf)
                .stream()
                .map(RepresentArticle::from)
                .toList();
    }

    private List<MentionRatio> toMentionRatios(List<MentionRatioRow> rows) {
        return rows.stream()
                .map(row -> new MentionRatio(
                        row.getCountryCode(),
                        row.getCountryName(),
                        row.getMentionRatio()))
                .toList();
    }
}
