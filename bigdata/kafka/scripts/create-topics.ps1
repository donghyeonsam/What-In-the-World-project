$KAFKA_CONTAINER = "news-kafka"
$BOOTSTRAP_SERVER = "kafka:29092"
$KAFKA_TOPICS = "/opt/kafka/bin/kafka-topics.sh"

Write-Host "Creating Kafka topics..."

docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --create `
    --if-not-exists `
    --topic news.raw.v1 `
    --partitions 6 `
    --replication-factor 1

docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --create `
    --if-not-exists `
    --topic news.enriched.v1 `
    --partitions 6 `
    --replication-factor 1

docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --create `
    --if-not-exists `
    --topic news.analytics.v1 `
    --partitions 3 `
    --replication-factor 1

docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --create `
    --if-not-exists `
    --topic news.unclassified.v1 `
    --partitions 6 `
    --replication-factor 1
docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --create `
    --if-not-exists `
    --topic news.event.v1 `
    --partitions 3 `
    --replication-factor 1
docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --delete `
    --topic news.analytics.v1
Write-Host ""
Write-Host "Kafka topics:"
docker exec $KAFKA_CONTAINER $KAFKA_TOPICS `
    --bootstrap-server $BOOTSTRAP_SERVER `
    --list