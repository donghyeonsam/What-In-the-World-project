package com.ssafy.witw.infra.kafka.dbwriter;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class DbWriterKafkaConsumerTest {

    private final ObjectMapper objectMapper = JsonMapper.builder()
            .findAndAddModules()
            .build();
    private final DbWriterService dbWriterService = mock(DbWriterService.class);
    private final DbWriterKafkaConsumer consumer = new DbWriterKafkaConsumer(
            objectMapper,
            dbWriterService
    );

    @Test
    void consumesNewsEventAndDelegatesWithKafkaKey() {
        String value = """
                {
                  "event_type": "ARTICLE_ISSUE_ASSIGNED",
                  "occurred_at": "2026-09-03T06:40:02Z",
                  "payload": {
                    "article_id": "a-123",
                    "issue_id": 102,
                    "similarity": 0.94
                  }
                }
                """;

        consumer.consume(new ConsumerRecord<>("news.event.v1", 1, 7L, "a-123", value));

        verify(dbWriterService).handle(
                new DbWriterEvent(
                        "ARTICLE_ISSUE_ASSIGNED",
                        java.time.OffsetDateTime.parse("2026-09-03T06:40:02Z"),
                        objectMapper.createObjectNode()
                                .put("article_id", "a-123")
                                .put("issue_id", 102)
                                .put("similarity", 0.94)
                )
        );
    }
}
