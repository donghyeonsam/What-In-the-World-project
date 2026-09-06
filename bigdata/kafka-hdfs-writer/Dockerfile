FROM gradle:9.1.0-jdk21 AS build

USER root
RUN mkdir -p /workspace && chown gradle:gradle /workspace
USER gradle
WORKDIR /workspace

COPY --chown=gradle:gradle settings.gradle build.gradle ./
COPY --chown=gradle:gradle src ./src

RUN gradle --no-daemon clean test installDist

FROM eclipse-temurin:21-jre

WORKDIR /app

RUN groupadd --system --gid 10001 writer \
    && useradd --system --uid 10001 --gid writer --create-home writer

COPY --from=build /workspace/build/install/kafka-hdfs-writer /app

USER writer

ENV HADOOP_CONF_DIR=/opt/hadoop-conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD kill -0 1

ENTRYPOINT ["/app/bin/kafka-hdfs-writer"]
