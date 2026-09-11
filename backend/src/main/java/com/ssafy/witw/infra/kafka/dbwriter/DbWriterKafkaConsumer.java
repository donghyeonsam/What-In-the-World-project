package com.ssafy.witw.infra.kafka.dbwriter;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Slf4j
@Component
@Profile("dev-prod")
@RequiredArgsConstructor
public class DbWriterKafkaConsumer {

    private final ObjectMapper objectMapper;
    private final DbWriterService dbWriterService;

    @KafkaListener(topics = "news.event.v1", groupId = "db-writer-v1")
    public void consume(ConsumerRecord<String, String> record) {
        DbWriterEvent event = deserialize(record.value());
        dbWriterService.handle(event);
    }

    private DbWriterEvent deserialize(String value) {
        try {
            return objectMapper.readValue(value, DbWriterEvent.class);
        } catch (JacksonException exception) {
            throw new IllegalArgumentException("Invalid news.event.v1 message", exception);
        }
    }
}
