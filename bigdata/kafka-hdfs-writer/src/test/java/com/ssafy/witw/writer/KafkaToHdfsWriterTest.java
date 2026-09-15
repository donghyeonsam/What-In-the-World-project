package com.ssafy.witw.writer;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KafkaToHdfsWriterTest {
    @Test
    void pendingBatchFlushesOnSizeRecordCountOrElapsedTime() {
        KafkaToHdfsWriter.PendingBatch batch = new KafkaToHdfsWriter.PendingBatch();
        batch.append("one", 100L);
        batch.append(null, 200L);

        assertEquals(2L, batch.recordCount());
        assertEquals("one\n".getBytes(StandardCharsets.UTF_8).length, batch.payloadBytes());
        assertTrue(batch.shouldFlush(200L, 4L, 100L, Duration.ofSeconds(10)));
        assertTrue(batch.shouldFlush(200L, 1_000L, 2L, Duration.ofSeconds(10)));
        assertTrue(batch.shouldFlush(101L, 1_000L, 100L, Duration.ofNanos(1L)));
        assertFalse(batch.shouldFlush(200L, 1_000L, 100L, Duration.ofSeconds(10)));
    }

    @Test
    void clearingBatchRemovesPayloadAndFlushState() {
        KafkaToHdfsWriter.PendingBatch batch = new KafkaToHdfsWriter.PendingBatch();
        batch.append("value", 100L);

        batch.clear();

        assertEquals(0L, batch.recordCount());
        assertEquals(0, batch.payloadBytes());
        assertFalse(batch.shouldFlush(10_000L, 1L, 1L, Duration.ofNanos(1L)));
    }
}
