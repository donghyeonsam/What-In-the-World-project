"""Resolve Spark Kafka and PostgreSQL dependencies during the image build."""

from pyspark.sql import SparkSession


# Docker 이미지 빌드에서만 실행된다. SparkSession이 생성되면 --packages로
# 지정된 Kafka Connector, JDBC Driver와 전이 의존성이 모두 내려받아진 상태다.
spark = (
    SparkSession.builder.master("local[1]")
    .appName("resolve-spark-kafka-dependencies")
    .getOrCreate()
)
spark.stop()
