package com.ssafy.witw.analysis.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

/**
 * 국가별 이슈 분석 작업을 비동기로 실행하기 위한 전용 Thread Pool 설정.
 *
 * 처음에는 Worker 1개로 순차 처리하고,
 * application.yml 설정만 변경해서 추후 2~3개 이상의 Worker로 확장할 수 있다.
 *
 * 이 Executor는 IssueCountryAnalysisWorkerService에서
 * @Async("issueCountryAnalysisExecutor")로 사용한다.
 */
@Configuration(proxyBeanMethods = false)
@EnableAsync
public class IssueCountryAnalysisAsyncConfig {

    /**
     * 기본으로 항상 유지할 Worker Thread 수.
     *
     * 현재 기본값은 1이므로 한 번에 하나의 국가별 분석 작업만 수행한다.
     */
    @Value("${analysis.worker.core-pool-size:1}")
    private int corePoolSize;

    /**
     * 동시에 생성할 수 있는 최대 Worker Thread 수.
     *
     * 현재 기본값은 1이며,
     * 추후 병렬 분석이 필요하면 application.yml에서 값을 늘릴 수 있다.
     */
    @Value("${analysis.worker.max-pool-size:1}")
    private int maxPoolSize;

    /**
     * 모든 Worker가 작업 중일 때 대기시킬 수 있는 분석 작업 수.
     *
     * 예:
     * Worker가 1개이고 Target이 20개라면
     * 1개는 실행되고 나머지는 Queue에서 순서대로 대기한다.
     */
    @Value("${analysis.worker.queue-capacity:100}")
    private int queueCapacity;

    /**
     * 국가별 이슈 분석 전용 Executor를 생성한다.
     *
     * 다른 @Async 작업과 Thread Pool을 공유하지 않고,
     * 이 분석 작업만 별도의 Worker Pool에서 처리하도록 Bean 이름을 지정한다.
     */
    @Bean(name = "issueCountryAnalysisExecutor")
    public Executor issueCountryAnalysisExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        // 동시에 유지할 기본 Worker 수
        executor.setCorePoolSize(corePoolSize);

        // 필요 시 생성할 수 있는 최대 Worker 수
        executor.setMaxPoolSize(maxPoolSize);

        // Worker가 모두 사용 중일 때 대기할 작업 수
        executor.setQueueCapacity(queueCapacity);

        // 로그에서 어떤 Thread가 분석 작업을 수행하는지 구분하기 위한 이름
        executor.setThreadNamePrefix("issue-country-analysis-");

        /*
         * 애플리케이션이 정상 종료될 때,
         * 이미 실행 중이거나 Queue에 들어간 작업을 즉시 중단하지 않고
         * 가능한 한 완료할 수 있도록 기다린다.
         */
        executor.setWaitForTasksToCompleteOnShutdown(true);

        // 종료 시 최대 30초 동안 작업 완료를 기다린다.
        executor.setAwaitTerminationSeconds(30);

        // ThreadPoolTaskExecutor 초기화
        executor.initialize();

        return executor;
    }
}