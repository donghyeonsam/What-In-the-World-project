package com.ssafy.witw.writer;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

public final class KafkaToHdfsWriter {
    private KafkaToHdfsWriter() {
    }

    public static void main(String[] args) throws Exception {
        // 환경 변수를 읽어옴
        String bootstrapServers = env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092");
        String topic = env("KAFKA_TOPIC", "news.enriched.v1");
        String groupId = env("KAFKA_GROUP_ID", "news-enriched-hdfs-silver-v1");
        String hdfsUri = env("HDFS_URI", "hdfs://namenode:9000");
        String outputPath = env(
                "HDFS_OUTPUT_PATH",
                "/data/news/silver/news.enriched.v1"
        );
        String hdfsUser = env("HDFS_USER", "root");
        String hadoopConfDirectory = env("HADOOP_CONF_DIR", "/opt/hadoop-conf");
        long maxBatchBytes = positiveLongEnv("HDFS_BATCH_MAX_BYTES", 64L * 1024 * 1024);
        long maxBatchRecords = positiveLongEnv("HDFS_BATCH_MAX_RECORDS", 50_000L);
        Duration flushInterval = Duration.ofSeconds(
                positiveLongEnv("HDFS_BATCH_FLUSH_INTERVAL_SECONDS", 300L)
        );

        // 연결할 hdfs 환경 설정
        Configuration hadoopConfiguration = new Configuration();
        hadoopConfiguration.addResource(new Path(hadoopConfDirectory + "/core-site.xml"));
        hadoopConfiguration.addResource(new Path(hadoopConfDirectory + "/hdfs-site.xml"));
        hadoopConfiguration.set("fs.defaultFS", hdfsUri);

        // Kafka Consumer 설정
        Properties kafkaProperties = new Properties();
        kafkaProperties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        kafkaProperties.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        kafkaProperties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        kafkaProperties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        kafkaProperties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        kafkaProperties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        kafkaProperties.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 500);

        try (
                // hdfs 연결
                FileSystem hdfs = FileSystem.get(URI.create(hdfsUri), hadoopConfiguration, hdfsUser);
                // consumer 생성
                KafkaConsumer<String, String> consumer = new KafkaConsumer<>(kafkaProperties)
        ) {
            // HDFS 출력 디렉터리 생성
            Path outputDirectory = new Path(outputPath);
            hdfs.mkdirs(outputDirectory);
            PendingBatch pendingBatch = new PendingBatch();

            // 설정된 토픽 구독
            consumer.subscribe(List.of(topic));
            while (true) {
                // 데이터가 없을 때만 최대 5초 기다린다. 데이터가 계속 들어와도 poll을
                // 유지해 consumer heartbeat를 보내고, 반환된 레코드는 HDFS 배치에 누적한다.
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofSeconds(5));
                long nowNanos = System.nanoTime();
                for (ConsumerRecord<String, String> record : records) {
                    pendingBatch.append(record.value(), nowNanos);
                }

                if (pendingBatch.shouldFlush(
                        nowNanos,
                        maxBatchBytes,
                        maxBatchRecords,
                        flushInterval
                )) {
                    flushBatch(hdfs, outputDirectory, consumer, pendingBatch);
                }
            }
        }
    }

    private static void flushBatch(
            FileSystem hdfs,
            Path outputDirectory,
            KafkaConsumer<String, String> consumer,
            PendingBatch pendingBatch
    ) throws IOException {
        long recordCount = pendingBatch.recordCount();
        int payloadBytes = pendingBatch.payloadBytes();

        if (payloadBytes > 0) {
            String fileName = "batch-%d-%s.jsonl".formatted(
                    System.currentTimeMillis(),
                    UUID.randomUUID()
            );
            Path temporaryFile = new Path(outputDirectory, "." + fileName + ".tmp");
            Path finalFile = new Path(outputDirectory, fileName);

            try (FSDataOutputStream output = hdfs.create(temporaryFile, false)) {
                pendingBatch.writeTo(output);
            }
            if (!hdfs.rename(temporaryFile, finalFile)) {
                throw new IOException("Could not complete HDFS file " + finalFile);
            }
        }

        // HDFS 쓰기와 rename이 완료된 데이터까지만 커밋한다. 커밋 전에 종료되면
        // Kafka가 같은 구간을 다시 전달하므로 유실 없이 중복만 허용한다.
        consumer.commitSync();
        pendingBatch.clear();
    }

    static byte[] toJsonLines(ConsumerRecords<String, String> records) {
        StringBuilder result = new StringBuilder();
        for (ConsumerRecord<String, String> record : records) {
            if (record.value() != null) {
                result.append(record.value()).append('\n');
            }
        }
        return result.toString().getBytes(StandardCharsets.UTF_8);
    }

    static final class PendingBatch {
        private final ByteArrayOutputStream payload = new ByteArrayOutputStream();
        private long recordCount;
        private long firstRecordNanos = -1L;

        void append(String value, long nowNanos) {
            if (recordCount == 0) {
                firstRecordNanos = nowNanos;
            }
            recordCount++;
            if (value != null) {
                payload.writeBytes(value.getBytes(StandardCharsets.UTF_8));
                payload.write('\n');
            }
        }

        boolean shouldFlush(
                long nowNanos,
                long maxBatchBytes,
                long maxBatchRecords,
                Duration flushInterval
        ) {
            if (recordCount == 0) {
                return false;
            }
            return payload.size() >= maxBatchBytes
                    || recordCount >= maxBatchRecords
                    || nowNanos - firstRecordNanos >= flushInterval.toNanos();
        }

        long recordCount() {
            return recordCount;
        }

        int payloadBytes() {
            return payload.size();
        }

        void writeTo(FSDataOutputStream output) throws IOException {
            payload.writeTo(output);
        }

        void clear() {
            payload.reset();
            recordCount = 0;
            firstRecordNanos = -1L;
        }
    }

    private static String env(String name, String defaultValue) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private static long positiveLongEnv(String name, long defaultValue) {
        String rawValue = env(name, Long.toString(defaultValue));
        try {
            long value = Long.parseLong(rawValue);
            if (value <= 0) {
                throw new IllegalArgumentException(name + " must be positive");
            }
            return value;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(name + " must be an integer", exception);
        }
    }
}
