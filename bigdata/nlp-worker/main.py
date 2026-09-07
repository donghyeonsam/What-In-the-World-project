"""
NLP Worker 실행 진입점.

Kafka의 news.raw.v1 토픽에서 원본 뉴스를 배치 단위로 읽고,
NLP 처리 결과를 추가한 뒤 news.enriched.v1 토픽으로 전송한다.
"""
from pipeline import process_article

from consumer import create_consumer, consume_batch
from producer import (
    create_producer,
    send_enriched_article,
    flush_producer,
)


# Kafka에서 읽어온 기사 배치를 NLP 파이프라인에 전달하고 처리 결과를 반환한다.
def process_batch(batch):
    processed_articles = []

    for item in batch:
        article = item["article"]

        processed_article = process_article(article)

        processed_articles.append(processed_article)

    return processed_articles


# NLP Worker를 실행하고 Kafka Consumer/Producer 처리 루프를 관리한다.
def main():
    consumer = create_consumer()
    producer = create_producer()

    print("NLP Worker started.")

    try:
        while True:
            # Kafka에서 최대 NLP_BATCH_SIZE개의 기사를 읽는다.
            batch = consume_batch(consumer)

            # 읽을 메시지가 없으면 다시 Kafka를 확인한다.
            if not batch:
                continue

            print(f"Consumed batch: {len(batch)} articles")

            # 읽어온 기사들을 NLP 처리한다.
            processed_articles = process_batch(batch)

            # NLP 처리 결과를 news.enriched.v1 토픽으로 전송한다.
            for article in processed_articles:
                send_enriched_article(producer, article)

            # Producer 내부 버퍼의 메시지가 모두 Kafka로 전송될 때까지 기다린다.
            flush_producer(producer)

            # NLP 처리와 Kafka 전송이 성공한 뒤 Consumer offset을 저장한다.
            consumer.commit(asynchronous=False)

            print(f"Processed batch: {len(batch)} articles")

    except KeyboardInterrupt:
        print("NLP Worker stopped.")

    finally:
        # 프로그램 종료 시 Kafka Consumer 연결을 안전하게 종료한다.
        consumer.close()


# 이 파일을 직접 실행했을 때 main() 함수를 시작한다.
if __name__ == "__main__":
    main()