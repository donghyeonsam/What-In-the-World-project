"""news.raw.v1 → archive → NLP → acknowledged news.enriched.v1 → commit."""
import logging
import signal

from pipeline import InvalidArticle, process_article
from storage.raw_archive import archive_batch
from consumer import create_consumer, consume_batch, commit_batch
from producer import create_producer, send_enriched_article, flush_producer

logger = logging.getLogger(__name__)


def process_batch(batch):
    processed = []
    for item in batch:
        message = item["message"]
        try:
            if item.get("invalid_reason"):
                raise InvalidArticle(item["invalid_reason"])
            processed.append(process_article(item["article"]))
        except InvalidArticle as exc:
            logger.warning(
                "Discarding invalid article topic=%s partition=%s offset=%s: %s",
                message.topic(), message.partition(), message.offset(), exc,
            )
    return processed


def handle_batch(consumer, producer, batch):
    if not batch:
        return
    # archive 실패는 기존 동작대로 종료. 부분 append/재처리 중복은 가능하다.
    archive_batch(batch)
    articles = process_batch(batch)
    for article in articles:
        send_enriched_article(producer, article)
    flush_producer(producer)
    commit_batch(consumer)
    logger.info("Batch committed: consumed=%d enriched=%d invalid=%d",
                len(batch), len(articles), len(batch) - len(articles))


def _stop_worker(signum, frame):
    raise KeyboardInterrupt


def main():
    logging.basicConfig(level=logging.INFO)
    consumer = create_consumer()
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGTERM, _stop_worker)
        producer = create_producer()
        logger.info("NLP Worker started; sentiment uses fixed dummy score 50.0")
        while True:
<<<<<<< HEAD
            handle_batch(consumer, producer, consume_batch(consumer))
=======
            # Kafka에서 최대 NLP_BATCH_SIZE개의 기사를 읽는다.
            batch = consume_batch(consumer)

            # 읽을 메시지가 없으면 다시 Kafka를 확인한다.
            if not batch:
                continue

            print(f"Consumed batch: {len(batch)} articles")

            # Kafka에서 읽어온 원본 기사 데이터를 JSONL 파일에 저장한다.
            archive_batch(batch)

            # 읽어온 기사들을 NLP 처리한다.
            processed_articles = process_batch(batch)

            # NLP 처리 결과를 news.enriched.v1 토픽으로 전송한다.
            for article in processed_articles:
                send_enriched_article(producer, article)

            # Producer 내부 버퍼의 메시지가 모두 Kafka로 전송될 때까지 기다린다.
            flush_producer(producer)

            # 원본 저장, NLP 처리, Kafka 전송이 성공한 뒤 Consumer offset을 저장한다.
            consumer.commit(asynchronous=False)

            print(f"Processed batch: {len(batch)} articles")

>>>>>>> master
    except KeyboardInterrupt:
        logger.info("Worker interrupted; unfinished batch will be replayed")
    except Exception:
        logger.exception("Worker failed; unfinished batch offsets are not committed")
        raise
    finally:
        # auto.commit=False이므로 close가 미완료 배치를 commit하지 않는다.
        try:
            consumer.close()
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    main()
