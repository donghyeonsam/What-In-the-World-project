package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisArticleRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisArticleRepository.ArticleForAnalysis;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisArticleService {

    private final IssueCountryAnalysisArticleRepository articleRepository;

    /**
     * 특정 이슈와 국가에 해당하는 분석용 기사를 기간 기준으로 조회한다.
     *
     * @param issueId     분석 대상 이슈 ID
     * @param countryCode 기사 발행 국가 코드
     * @param periodStart 분석 시작 시각
     * @param periodEnd   분석 종료 시각
     * @return 분석에 사용할 기사 목록
     */
    @Transactional(readOnly = true)
    public List<ArticleForAnalysis> findArticles(
            long issueId,
            String countryCode,
            LocalDateTime periodStart,
            LocalDateTime periodEnd
    ) {
        return articleRepository.findArticles(
                issueId,
                countryCode,
                periodStart,
                periodEnd
        );
    }
}