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
            handle_batch(consumer, producer, consume_batch(consumer))
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
