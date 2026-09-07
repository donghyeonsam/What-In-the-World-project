package com.ssafy.witw.domain.article.service;

import com.ssafy.witw.domain.article.dao.ArticleRepository;
import com.ssafy.witw.domain.article.dto.GlobalArticleCountResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ArticleService {

    private final ArticleRepository articleRepository;

    @Transactional(readOnly = true)
    public GlobalArticleCountResponse getArticleCount() {
        return new GlobalArticleCountResponse(
                getTotalArticlesCount(),
                getArticleCountLast24Hours(null, null),
                LocalDateTime.now());
    }

    // countryCode가 null이면 국가 전체, issueId가 없으면 모든 기사 개수를 반환
    private long getArticleCountLast24Hours(String countryCode, Long issueId) {
        return articleRepository.countArticlesLast24Hours(countryCode, issueId);
    }

    private long getTotalArticlesCount() {
        return articleRepository.countByDeletedAtIsNull();
    }
}
