package com.ssafy.witw.domain.article.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dto.GlobalArticleCountResponse;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.service.IssueService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ArticleService {

    private final ArticleRepository articleRepository;
    private final IssueRepository issueRepository;
    private final CountryRepository countryRepository;

    public GlobalArticleCountResponse getArticleCount() {
        return new GlobalArticleCountResponse(
                getTotalArticlesCount(),
                getArticleCountLast24Hours(null, null),
                LocalDateTime.now());
    }

    // countryCode가 null이면 국가 전체, issueId가 없으면 모든 기사 개수를 반환
    private long getArticleCountLast24Hours(String countryCode, Long issueId) {

        // 나라 코드에 해당하는 나라가 없는 경우
        if (countryCode != null && countryRepository.existsById(countryCode)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        // issueID에 해당하는 issueId가 없는 경우
        if (issueId != null && issueRepository.existsById(issueId)) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }

        return articleRepository.countArticlesLast24Hours(countryCode, issueId);
    }

    private long getTotalArticlesCount() {
        return articleRepository.countByDeletedAtIsNull();
    }
}
