"""
NLP Worker 실행 진입점.

Kafka에서 뉴스를 배치 단위로 읽고,
NLP 파이프라인을 실행한 뒤 처리 결과를 Kafka로 전송한다.
"""