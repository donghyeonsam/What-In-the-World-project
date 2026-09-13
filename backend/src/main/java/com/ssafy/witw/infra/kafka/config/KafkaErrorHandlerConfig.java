package com.ssafy.witw.infra.kafka.config;

import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOff;

/**
 * DbWriter 컨슈머의 실패 처리 정책.
 *
 * <p>기본 {@code DefaultErrorHandler}는 {@code FixedBackOff(interval=0, 9회)}로 동작해
 * 약 1초 만에 재시도를 소진한 뒤 레코드를 <b>흔적 없이 폐기</b>하고 오프셋을 커밋한다.
 * 2026-09-10~09-11에 10,794건이 이 경로로 소실됐으나 DLT도 알림도 없어 인지되지 못했다.
 *
 * <p>이 설정은 두 가지를 바꾼다.
 * <ul>
 *   <li>일시적 오류(DB 커넥션 고갈, 데드락 등)에는 지수 백오프로 실제 회복 시간을 준다.</li>
 *   <li>재시도해도 소용없는 오류(페이로드 불량, 참조 데이터 부재)는 즉시 DLT로 보내
 *       파티션을 막지 않으면서 유실 사실을 보존한다.</li>
 * </ul>
 */
@Slf4j
@Configuration
@Profile("dev-prod")
public class KafkaErrorHandlerConfig {

    private static final String SOURCE_TOPIC = "news.event.v1";
    private static final String DLT_TOPIC = SOURCE_TOPIC + ".dlt";

    /**
     * 브로커가 {@code auto.create.topics.enable=false}이므로 DLT를 명시적으로 선언한다.
     * 원본과 동일한 파티션 수를 유지해 키 기반 분산을 보존한다.
     */
    @Bean
    public NewTopic dbWriterDeadLetterTopic() {
        return TopicBuilder.name(DLT_TOPIC)
                .partitions(3)
                .replicas(1)
                .build();
    }

    @Bean
    // Boot의 KafkaTemplate 빈은 KafkaTemplate<?, ?>로 선언된다.
    // <Object, Object>로 주입하면 제네릭 매칭이 버전에 따라 실패할 수 있으므로 와일드카드로 받는다.
    public DefaultErrorHandler dbWriterErrorHandler(KafkaTemplate<?, ?> kafkaTemplate) {
        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> {
                    log.error("DLT 전송: topic={} partition={} offset={} key={} cause={}",
                            record.topic(), record.partition(), record.offset(),
                            record.key(), exception.getMessage());
                    // 파티션 -1: DLT 파티션 수가 달라져도 브로커가 배정하도록 위임한다.
                    return new TopicPartition(DLT_TOPIC, -1);
                }
        );

        // Spring Framework 7부터 ExponentialBackOffWithMaxRetries가 ExponentialBackOff로 통합됐다.
        ExponentialBackOff backOff = new ExponentialBackOff();
        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(8_000L);
        backOff.setMaxAttempts(4);
        backOff.setJitter(200L);   // 다수 레코드가 동시에 재시도해 DB에 몰리는 것을 방지

        DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);

        // 아래 예외는 재시도해도 결과가 같다. 즉시 DLT로 보내 파티션 지연을 막는다.
        //  - IllegalArgumentException : 역직렬화 실패, 페이로드 규격 위반
        //  - IllegalStateException    : country/theme 미등록, ISSUE_CREATE의 기사 미존재
        handler.addNotRetryableExceptions(
                IllegalArgumentException.class,
                IllegalStateException.class
        );

        return handler;
    }
}
