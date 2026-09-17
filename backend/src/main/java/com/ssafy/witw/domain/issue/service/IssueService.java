package com.ssafy.witw.domain.issue.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.dto.CountryPoint;
import com.ssafy.witw.domain.country.dto.CountryTone;
import com.ssafy.witw.domain.issue.dao.IssueRepository.CountryToneRow;
import com.ssafy.witw.domain.issue.dao.IssueRepository.GlobalIssueRankRow;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.dto.GlobalIssueDetailResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse.GlobalIssue;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse;
import com.ssafy.witw.domain.issue.dto.IssueInfo;
import com.ssafy.witw.domain.issue.dto.IssueOverviewResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class IssueService {

    private static final int MAX_ARTICLE_LIMIT = 10;

    @Value("${analysis.top-issue-limit:5}")
    private int globalIssueRankLimit = 5;

    private final IssueRepository issueRepository;
    private final ArticleRepository articleRepository;

    public IssueOverviewResponse getIssueOverview(long issueId, int articleLimit) {
        return getIssueOverview(issueId, articleLimit, null, QueryTime.now());
    }

    public IssueOverviewResponse getIssueOverview(long issueId, int articleLimit, String countryCode) {
        return getIssueOverview(issueId, articleLimit, countryCode, QueryTime.now());
    }

    public IssueOverviewResponse getIssueOverview(long issueId, int articleLimit, String countryCode, LocalDateTime asOf) {
        if (articleLimit < 1 || articleLimit > MAX_ARTICLE_LIMIT) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
        if (!issueRepository.existsById(issueId)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        IssueRepository.IssuePreview preview = issueRepository.getIssuePreviewByIssueId(issueId, asOf);
        if (preview == null) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        IssueOverviewResponse.IssuePreview issuePreview = new IssueOverviewResponse.IssuePreview(
                preview.getIssueTitle(), preview.getThemeTitle(), preview.getArticleCount());

        List<CountryTone> countryTones = issueRepository.findCountryTonesLast24Hours(issueId, asOf)
                .stream()
                .map(this::toCountryTone)
                .toList();

        List<ArticleRepository.RepresentArticleProjection> articleRows = countryCode == null
                ? articleRepository.getRepresentArticlesByIssueId(issueId, articleLimit, asOf)
                : articleRepository.getRepresentArticlesByIssueIdAndCountryCode(issueId, countryCode, articleLimit, asOf);
        List<RepresentArticle> representArticles = articleRows
                .stream()
                .map(RepresentArticle::from)
                .toList();

        return new IssueOverviewResponse(issuePreview, countryTones, representArticles);
    }

    public GlobalIssueRankResponse getGlobalIssueRank() {
        long totalArticleCount = articleRepository.countByDeletedAtIsNull();
        long recent24ArticleCount = articleRepository.countArticlesLast24Hours(null, null);
        List<GlobalIssue> globalIssues = issueRepository.findGlobalIssueRankLast24Hours(globalIssueRankLimit)
                .stream()
                .map(this::toGlobalIssue)
                .toList();

        return new GlobalIssueRankResponse(totalArticleCount, recent24ArticleCount, globalIssues);
    }

    // 글로벌 이슈 상세는 대표 기사를 쓰지 않으므로 프리뷰(getIssueOverview)와 별도로 조회한다
    public GlobalIssueDetailResponse getGlobalIssueDetail(long issueId) {
        return getGlobalIssueDetail(issueId, QueryTime.now());
    }

    public GlobalIssueDetailResponse getGlobalIssueDetail(long issueId, LocalDateTime asOf) {
        // findIssueById 가 LEFT JOIN 이라 null 은 이슈 미존재를 뜻한다
        IssueInfo issueInfo = issueRepository.findIssueById(issueId, asOf);
        if (issueInfo == null) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        List<CountryTone> countryTones = issueRepository.findCountryTonesLast24Hours(issueId, asOf)
                .stream()
                .map(this::toCountryTone)
                .toList();

        return new GlobalIssueDetailResponse(issueInfo, countryTones);
    }

    private GlobalIssue toGlobalIssue(GlobalIssueRankRow row) {
        return new GlobalIssue(
                row.getIssueId(),
                row.getFieldName(),
                row.getThemeName(),
                row.getIssueName(),
                row.getArticleCount(),
                row.getFirstSeenAt()
        );
    }

    private CountryTone toCountryTone(CountryToneRow row) {
        CountryPoint country = new CountryPoint(
                row.getCountryCode(),
                row.getCountryName(),
                row.getLongitude(),
                row.getLatitude()
        );

        return new CountryTone(
                country,
                row.getToneAvg(),
                row.getToneMax(),
                row.getToneMin(),
                row.getToneSd(),
                row.getArticleCount()
        );
    }

}
