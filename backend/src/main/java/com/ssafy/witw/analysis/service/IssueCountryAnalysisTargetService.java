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

    // .yml에서 관리 중. 값을 변경하면 그걸로 TOP N이 반영
    @Value("${analysis.top-issue-limit:5}")
    private int topIssueLimit = 5;

    // .yml에서 관리 중. 하나의 이슈와 국가에 대해 24시간 기준 몇 건의 기사가 있어야 하는지 기준치
    @Value("${analysis.min-country-articles:10}")
    private int minCountryArticleCount = 10;

    private final IssueCountryAnalysisTargetRepository targetRepository;

    @Transactional(readOnly = true)
    public List<Target> findTargets(LocalDateTime periodStart, LocalDateTime periodEnd) {
        // 최근 24시간의 글로벌 이슈 TOP N의 ID와 거기 포함된 국가들 중 min값 이상의 국가코드를 조회해서 반환
        return targetRepository.findTargets(
                periodStart,
                periodEnd,
                topIssueLimit,
                minCountryArticleCount
        );
    }
}
