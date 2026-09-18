package com.ssafy.witw.domain.issue.service;

import com.ssafy.witw.common.time.QueryTime;
import com.ssafy.witw.domain.issue.dao.IssueHeatScoreStore;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Slf4j
@Service
@Profile("!test")
@RequiredArgsConstructor
public class IssueHeatScoreRefreshService {

    private final IssueHeatScoreStore scoreStore;

    @Scheduled(
            // 5분마다 핫이슈 랭킹 갱신
            fixedDelayString = "${witw.issue-heat.refresh-ms:300000}",
            // 서버 시작 후에 바로 랭킹 갱신
            initialDelayString = "${witw.issue-heat.initial-delay-ms:1000}"
    )
    @Transactional
    public void refresh() {
        LocalDateTime calculatedAt = QueryTime.now();
        int countryScores = scoreStore.appendCountryScores(calculatedAt);
        int globalScores = scoreStore.appendGlobalScores(calculatedAt);
        log.info("핫이슈 점수 스냅샷 생성 완료: calculatedAt={}, countryScores={}, globalScores={}",
                calculatedAt, countryScores, globalScores);
    }
}
