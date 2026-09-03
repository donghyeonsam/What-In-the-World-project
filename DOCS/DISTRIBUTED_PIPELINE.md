# 분산처리 파이프라인 정리

![Pipeline v1](./image/pipeline_v1.png)

#### 바로가기

- [1. 뉴스 수집기](#1-뉴스-수집기)
- [2. Kafka(news.raw)](#2-kafkanewsraw)
- [3. NLP worker](#3-nlp-worker)
- [4. Kafka(news.enriched)](#4-kafkanewsenriched)
- [5. Spark(기사 분석용)](#5-spark기사-분석용)
- [6. 이슈 매칭](#6-이슈-매칭)
  - [6-1. Kafka(news.unclassified)](#6-1-kafkanewsunclassified)
  - [6-2. Spark(이슈 클러스터링용)](#6-2-spark이슈-클러스터링용)
- [7. Kafka(news.event)](#7-kafkanewsevent)
- [8. Database 저장](#8-database-저장)
- [9. 이벤트 테이블 저장](#9-이벤트-테이블-저장)


## 1. 뉴스 수집기


## 2. Kafka(news.raw)


## 3. NLP worker


## 4. Kafka(news.enriched)


## 5. Spark(기사 분석용)


## 6. 이슈 매칭


### 6-1. Kafka(news.unclassified)


### 6-2. Spark(이슈 클러스터링용)


## 7. Kafka(news.event)


## 8. Database 저장


## 9. 이벤트 테이블 저장