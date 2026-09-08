ARG SPARK_BASE_IMAGE=apache/spark:4.2.0-python3

# 운영 컨테이너가 시작할 때 Maven Central에 접근하지 않도록 빌드 단계에서
# Spark Kafka Connector와 전이 의존성을 모두 Ivy 캐시에 내려받는다.
FROM ${SPARK_BASE_IMAGE} AS kafka-dependency-resolver

USER root

COPY resolve_kafka_dependencies.py /tmp/resolve_kafka_dependencies.py

RUN /opt/spark/bin/spark-submit \
        --master 'local[1]' \
        --conf spark.jars.ivy=/tmp/.ivy2 \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0 \
        /tmp/resolve_kafka_dependencies.py


# Master, Worker, Streaming Driver가 동일한 JAR 구성을 갖도록 같은 최종
# 이미지를 사용한다. 최종 이미지에는 Ivy 캐시가 아니라 실행에 필요한 JAR만 남긴다.
FROM ${SPARK_BASE_IMAGE}

USER root

COPY --from=kafka-dependency-resolver /tmp/.ivy2/jars/ /opt/spark/jars/

USER spark
