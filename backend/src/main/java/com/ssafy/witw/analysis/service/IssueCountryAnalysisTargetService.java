package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class IssueCountryAnalysisTargetService {

    @Value("${analysis.top-issue-limit:5}")
    private int topIssueLimit = 5;

    @Value("${analysis.min-country-articles:10}")
    private int minCountryArticleCount = 10;

    private final IssueCountryAnalysisTargetRepository targetRepository;

    @Transactional(readOnly = true)
    public List<Target> findTargets(LocalDateTime periodStart, LocalDateTime periodEnd) {
        return targetRepository.findTargets(
                periodStart,
                periodEnd,
                topIssueLimit,
                minCountryArticleCount
        );
    }
}
