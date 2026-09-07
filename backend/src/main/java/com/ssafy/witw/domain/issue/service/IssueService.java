package com.ssafy.witw.domain.issue.service;

import com.ssafy.witw.domain.country.dto.CountryPoint;
import com.ssafy.witw.domain.country.dto.CountryTone;
import com.ssafy.witw.domain.country.dto.CountryToneResponse;
import com.ssafy.witw.domain.issue.dao.IssueRepository;
import com.ssafy.witw.domain.issue.dao.IssueRepository.CountryToneRow;
import com.ssafy.witw.domain.issue.dao.IssueRepository.GlobalIssueRankRow;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse;
import com.ssafy.witw.domain.issue.dto.GlobalIssueRankResponse.GlobalIssue;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class IssueService {

    private static final int GLOBAL_ISSUE_RANK_LIMIT = 5;

    private final IssueRepository issueRepository;

    // 최근 24시간 기사 수 기준 이슈 랭킹
    public GlobalIssueRankResponse getGlobalIssueRank() {

        List<GlobalIssue> globalIssues =
                issueRepository.findGlobalIssueRankLast24Hours(GLOBAL_ISSUE_RANK_LIMIT)
                        .stream()
                        .map(this::toGlobalIssue)
                        .toList();

        return new GlobalIssueRankResponse(globalIssues);
    }

    // 목록에서 이슈를 선택했을 때의 국가별 톤
    public CountryToneResponse getCountryTones(long issueId) {

        List<CountryTone> countryTones = issueRepository.findCountryTonesLast24Hours(issueId)
                .stream()
                .map(this::toCountryTone)
                .toList();

        return new CountryToneResponse(countryTones);
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
}
