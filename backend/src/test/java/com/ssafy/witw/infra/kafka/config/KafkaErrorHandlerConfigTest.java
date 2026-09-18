package com.ssafy.witw.infra.kafka.config;

import org.apache.kafka.clients.admin.NewTopic;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.kafka.autoconfigure.KafkaAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DefaultErrorHandler;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 브로커 없이 빈 배선만 검증한다.
 * 컴파일 통과가 컨텍스트 기동을 보장하지 않으므로(제네릭 매칭 실패 등) 별도로 확인한다.
 */
class KafkaErrorHandlerConfigTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(KafkaAutoConfiguration.class))
            .withUserConfiguration(KafkaErrorHandlerConfig.class)
            .withPropertyValues(
                    "spring.profiles.active=dev-prod",
                    "spring.kafka.bootstrap-servers=localhost:9092",
                    "spring.kafka.admin.auto-create=false"
            );

    @Test
    @DisplayName("dev-prod 프로파일에서 에러 핸들러와 DLT 토픽 빈이 생성된다")
    void createsErrorHandlerAndDltTopic() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DefaultErrorHandler.class);
            assertThat(context.getBean(DefaultErrorHandler.class))
                    .isInstanceOf(CommonErrorHandler.class);

            NewTopic dlt = context.getBean(NewTopic.class);
            assertThat(dlt.name()).isEqualTo("news.event.v1.dlt");
            assertThat(dlt.numPartitions()).isEqualTo(3);
        });
    }

    @Test
    @DisplayName("dev-prod가 아닌 프로파일에서는 빈이 생성되지 않는다")
    void notCreatedOnOtherProfiles() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(KafkaAutoConfiguration.class))
                .withUserConfiguration(KafkaErrorHandlerConfig.class)
                .withPropertyValues("spring.profiles.active=prod",
                        "spring.kafka.bootstrap-servers=localhost:9092")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(DefaultErrorHandler.class);
                });
    }
}
