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
        String topic = env("KAFKA_TOPIC", "news.raw.v1");
        String groupId = env("KAFKA_GROUP_ID", "news-raw-hdfs-bronze-v1");
        String hdfsUri = env("HDFS_URI", "hdfs://namenode:9000");
        String outputPath = env(
                "HDFS_OUTPUT_PATH",
                env("HDFS_BRONZE_PATH", "/data/news/bronze/news.raw.v1")
        );
        String hdfsUser = env("HDFS_USER", "root");
        String hadoopConfDirectory = env("HADOOP_CONF_DIR", "/opt/hadoop-conf");

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

            // 설정된 토픽 구독
            consumer.subscribe(List.of(topic));
            while (true) {
                // 데이터를 가져올 때 최대 5초까지 기다린다 (5초 동안 최대 MAX_POLL만큼의 레코드를 받을 수 있음)
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofSeconds(5));
                if (records.isEmpty()) {
                    continue;
                }

                byte[] jsonLines = toJsonLines(records);
                // 파일명이 겹치지 않게 UUID로 설정
                String fileName = "batch-%d-%s.jsonl".formatted(
                        System.currentTimeMillis(),
                        UUID.randomUUID()
                );
                // 임시 파일과 최종 파일 구조 생성 (아직 실제로 만들어지진 않음)
                Path temporaryFile = new Path(outputDirectory, "." + fileName + ".tmp");
                Path finalFile = new Path(outputDirectory, fileName);

                // 임시 파일에 내용을 기록
                try (FSDataOutputStream output = hdfs.create(temporaryFile, false)) {
                    output.write(jsonLines);
                }
                // 완전히 내용이 다 임시 파일에 작성이 되면, 그때 최종 파일로 덮어쓰기 -> 최종 파일은 무조건 완전한 상태일 때만 나타남
                if (!hdfs.rename(temporaryFile, finalFile)) {
                    throw new IllegalStateException("Could not complete HDFS file " + finalFile);
                }
                // 성공적으로 최종 파일이 만들어지면 커밋 -> offset 갱신
                consumer.commitSync();
            }
        }
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

    private static String env(String name, String defaultValue) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? defaultValue : value;
    }
}
