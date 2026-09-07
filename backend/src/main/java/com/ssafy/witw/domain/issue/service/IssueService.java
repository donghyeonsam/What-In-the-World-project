package com.ssafy.witw.domain.issue.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dao.ArticleRepository.RepresentArticleProjection;
import com.ssafy.witw.domain.article.dto.ArticleTone;
import com.ssafy.witw.domain.article.dto.RepresentArticle;
import com.ssafy.witw.domain.country.dto.CountryPoint;
import com.ssafy.witw.domain.country.dto.CountryTone;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.dao.IssueRepository.CountryToneRow;
import com.ssafy.witw.domain.issue.dao.IssueRepository.GlobalIssueRankRow;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse.GlobalIssue;
import com.ssafy.witw.domain.issue.dto.IssueInfo;
import com.ssafy.witw.domain.issue.dto.IssueOverviewResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class IssueService {

    private static final int GLOBAL_ISSUE_RANK_LIMIT = 5;
    private static final int REPRESENT_ARTICLE_LIMIT = 3;

    private final IssueRepository issueRepository;
    private final ArticleRepository articleRepository;

    public IssueOverviewResponse getIssueOverview(long issueId, int articleLimit) {
        if (!issueRepository.existsById(issueId)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        IssueRepository.IssuePreview preview = issueRepository.getIssuePreviewByIssueId(issueId);
        if (preview == null) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        IssueOverviewResponse.IssuePreview issuePreview = new IssueOverviewResponse.IssuePreview(
                preview.getIssueTitle(), preview.getThemeTitle(), preview.getArticleCount());

        List<CountryTone> countryTones = issueRepository.findCountryTonesLast24Hours(issueId)
                .stream()
                .map(this::toCountryTone)
                .toList();

        List<RepresentArticle> representArticles = articleRepository
                .getRepresentArticlesByIssueId(issueId, articleLimit)
                .stream()
                .map(this::toRepresentArticle)
                .toList();

        return new IssueOverviewResponse(issuePreview, countryTones, representArticles);
    }

    // 최근 24시간 기사 수 기준 이슈 랭킹
    public GlobalIssueRankResponse getGlobalIssueRank() {
        List<GlobalIssue> globalIssues = issueRepository.findGlobalIssueRankLast24Hours(GLOBAL_ISSUE_RANK_LIMIT)
                        .stream()
                        .map(this::toGlobalIssue)
                        .toList();
        return new GlobalIssueRankResponse(globalIssues);
    }

    // 이슈 카드 UI에 사용(이슈명, 관련 기사 개수, 관련 나라 개수)
    public IssueInfo getIssueInfo(long issueId) {
        if (!issueRepository.existsById(issueId)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }
        return issueRepository.findIssueById(issueId);
    }

    public Double getGlobalTone(long issueId) {
        return issueRepository.findGlobalToneById(issueId);
    }

    public List<CountryTone> getCountryTones(long issueId) {
        if (!issueRepository.existsById(issueId)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }
        return issueRepository.findCountryTonesLast24Hours(issueId).stream()
                .map(this::toCountryTone)
                .toList();
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
                row.getToneMin()
        );
    }

    private RepresentArticle toRepresentArticle(RepresentArticleProjection row) {
        return new RepresentArticle(
                row.getArticleId(),
                row.getArticleTitle(),
                ArticleTone.fromScore(row.getArticleToneScore()),
                row.getArticlePublisher(),
                row.getPublishedAt()
        );
    }
}
