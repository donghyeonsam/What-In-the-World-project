# 분산처리 파이프라인 정리

![Pipeline v1](./image/pipeline_v1.png)

### 바로가기<hr>

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

<hr>


## 1. 뉴스 수집기
뉴스 수집기는 전 세계 언론사의 뉴스 데이터를 수집하여 Kafka의 `news.raw` 토픽으로 전달하는 역할을 담당한다.

### 1-1. 수집 대상 언론사 선정<hr>
전 세계 언론사 정보는 MediaCloud를 통해 확인한다.

MediaCloud에서 확보한 전체 언론사 목록을 기반으로, 프로젝트 초기 단계에서는 우선 5개 국가의 언론사만 수집 대상으로 선정한다.

- **초기 대상 국가**: 한국, 미국, 일본, 영국, 독일<br>
- **초기 수집 언론사 수**: 약 330개

이후 각 언론사의 뉴스 제공 방식을 확인하여 다음 두 가지 방식으로 수집 가능한 언론사만 최종 목록에 포함한다.

- **RSS**
- **Sitemap**

즉, 전체 언론사 목록을 그대로 매번 조회하는 것이 아니라 아래와 같은 과정을 통해 수집 가능한 언론사 목록을 사전에 구성한다.

생성된 언론사 목록은 이후 반복적으로 활용한다.
<hr>

### 1-2. 뉴스 수집 주기<hr>
뉴스 수집은 10분 주기로 실행된다.

- 수집 시작
- 언론사 목록 조회
- 각 언론사의 RSS / Sitemap 확인
- 새롭게 등록된 기사 탐색
- 기사 본문 및 메타데이터 수집

수집기는 사전에 구성된 언론사 목록을 기준으로 각 언론사의 RSS 또는 Sitemap을 확인하며, 새롭게 발견된 기사만 수집한다.

### 1-3. 수집 방식<hr>
언론사<br>
  │<br>
  ├─ RSS 지원 ───────► RSS 기반 기사 탐색<br>
  │<br>
  └─ Sitemap 지원 ──► Sitemap 기반 기사 탐색<br>

하나의 언론사가 여러 수집 Endpoint를 제공할 수 있으며, 수집기는 각 Endpoint를 기준으로 새로운 기사 URL을 탐색한다.

### 1-4. 수집 결과<hr>
새로운 기사가 발견되면 기사 본문과 함께 수집에 필요한 메타데이터를 생성한다.

수집 결과 예시는 다음과 같다.

```json
{
	"source_id":"622913",
	"source_name":"Hankook Ilbo - South Korea (Korean)",
	"country":"South Korea",
	"article_url":"https://www.hankooki.com/news/articleView.html?idxno=342372",
	"published_at": "2026-09-01T08:15:03+00:00",
	"discovered_at": "2026-09-01T08:22:28.256121+00:00",
	"discovery_type":"SITEMAP",
	"endpoint_url":"https://www.hankooki.com/sitemap.xml",
	"success":true,
	"http_status":200,
	"title":"국가철도공단, 정진혁 신임 이사장 취임…CEO 공백 종료",
	"body":"[데일리한국 정백현 기자] 5개월여 간 공백이었던 국가철도공단의 새 이사장에...",
	"body_length":1036,
	"elapsed_ms":87,
	"error": null
}
```
## 2. Kafka(news.raw)
뉴스 수집기가 수집한 기사는 Kafka를 통해 다음 처리 단계로 전달한다.

Kafka는 각 처리 컴포넌트 사이에서 메시지를 전달하는 역할을 하며, 특정 Consumer의 처리 속도가 느려지더라도 Producer와 직접적으로 결합되지 않도록 한다.

news.raw.v1<br>
 │<br>
 ├──► NLP Worker<br>
 │<br>
 └──► HDFS 저장 처리

### 2-1. Topic 정보
| 항목 | 내용 |
| --- | --- |
| Topic | `news.raw.v1` |
| Producer | 뉴스 수집기 |
| Consumer | NLP Worker, HDFS 저장 처리 |
| Partition | 6 |

`news.raw`에는 기사 원문과 수집 단계에서 생성된 메타데이터가 저장된다.


## 3. NLP worker


## 4. Kafka(news.enriched)


## 5. Spark(기사 분석용)


## 6. 이슈 매칭
## 데이터 입력

NLP 처리가 완료된 기사에는 이슈 매칭에 필요한 `theme_id`와 `embedding` 정보가 포함되어 있다.

```json
{
  "article_id": "a-123",
  "theme_id": 12,
  "embedding": [0.031, -0.114, 0.072],
  "title": "미국, 대중국 AI 반도체 수출 규제 확대",
  "summary": "미국이 중국 대상 AI 반도체 수출 규제를 확대했다.",
  "published_at": "2026-09-03T03:35:24Z"
}
```

Spark는 10분 단위 Micro Batch로 새롭게 유입된 기사들을 처리한다.

예를 들어 한 Micro Batch에 다음 테마의 기사들이 포함되어 있다고 가정한다.

```
SEMICONDUCTOR
AI
TRADE
```

---

## 기존 활성 이슈 조회

새롭게 유입된 기사와 비교하기 위해 해당 기사들이 속한 Theme의 기존 활성 이슈를 PostgreSQL에서 조회한다.

```sql
SELECT
    id AS issue_id,
    theme_id,
    centroid_embedding
FROM issue
WHERE theme_id IN (12, 15, 21)
  AND status = 'ACTIVE';
```

필요한 경우 최근 일정 기간 내 활성화된 이슈만 조회한다.

```sql
AND last_seen_at >= NOW() - INTERVAL '72 hours'
```

Spark에서는 JDBC를 이용하여 이슈 정보를 조회한다.

```python
issues_df = (
    spark.read
    .format("jdbc")
    .option("url", postgres_url)
    .option("query", query)
    .option("user", postgres_user)
    .option("password", postgres_password)
    .option("driver", "org.postgresql.Driver")
    .load()
)
```

최종적으로 다음과 같은 형태의 DataFrame을 얻는다.

```
+----------+----------+--------------------+
| issue_id | theme_id | centroid_embedding |
+----------+----------+--------------------+
| 101      | 12       | [...]              |
| 102      | 12       | [...]              |
| 201      | 15       | [...]              |
+----------+----------+--------------------+
```

## 같은 Theme의 Issue끼리 후보 생성

기사와 모든 이슈를 비교하는 것이 아니라, 동일한 `theme_id`를 가진 이슈만 비교 대상으로 설정한다.

예를 들어 다음과 같은 형태가 된다.

```
+------------+----------+----------+------------------+--------------------+
| article_id | theme_id | issue_id | embedding        | centroid_embedding |
+------------+----------+----------+------------------+--------------------+
| a-123      | 12       | 101      | [article...]     | [issue101...]      |
| a-123      | 12       | 102      | [article...]     | [issue102...]      |
| a-124      | 15       | 201      | [article...]     | [issue201...]      |
+------------+----------+----------+------------------+--------------------+
```

이를 통해 서로 다른 Theme에 속한 이슈와의 불필요한 유사도 계산을 방지한다.

---

## Cosine Similarity 계산

각 기사 embedding과 Issue의 `centroid_embedding` 사이의 Cosine Similarity를 계산한다.

```
article a-123
      │
      ├── issue-101 centroid → 0.94
      │
      └── issue-102 centroid → 0.81
```

계산 이후에는 다음과 같은 형태가 된다.

```
+------------+----------+----------+------------+
| article_id | theme_id | issue_id | similarity |
+------------+----------+----------+------------+
| a-123      | 12       | 101      | 0.94       |
| a-123      | 12       | 102      | 0.81       |
| a-124      | 15       | 201      | 0.87       |
+------------+----------+----------+------------+
```

---

## 기사별 최고 유사도 Issue 선택

하나의 기사가 여러 Issue와 비교되기 때문에 기사마다 가장 높은 similarity를 가진 Issue 하나를 선택한다.

```
+------------+----------+----------+------------+
| article_id | theme_id | issue_id | similarity |
+------------+----------+----------+------------+
| a-123      | 12       | 101      | 0.94       |
| a-124      | 15       | 201      | 0.87       |
+------------+----------+----------+------------+
```

---

## Issue 매칭 여부 판단

최고 similarity를 기준으로 기존 Issue와의 매칭 여부를 판단한다.

유사도가 90이상인지 판단해서, 분기처리한다.

```
similarity >= 0.90
    → 기존 Issue 매칭

similarity < 0.90
    → 미분류 기사
```

---

## Issue 매칭 성공

기존 Issue와 매칭된 경우 `ARTICLE_ISSUE_ASSIGNED` 이벤트를 생성한다.

```json
{
  "event_id": "event-uuid-002",
  "event_type": "ARTICLE_ISSUE_ASSIGNED",
  "occurred_at": "2026-09-03T06:40:02Z",
  "payload": {
    "article_id": "87fa2c9...",
    "issue_id": 102,
    "similarity": 0.94
  }
}
```

Kafka Key는 `article_id`를 사용한다.

```
key = article_id
```

동일 기사에 대한 이벤트가 동일 Partition으로 전달되도록 한다.

해당 이벤트는 후속 DB Writer가 소비하여 기사와 Issue의 관계를 저장한다.

---

## Issue 매칭 실패

이슈가 매칭되지 않은 기사들은 따로 관리한다.

### 6-1. Kafka(news.unclassified)
# 6-1. 미분류 기사 상태 저장

`news.unclassified` Kafka에는 미분류 기사 발생 이벤트를 전달한다.

```
key = theme_id
```

```json
{
  "article_id": "a-123",
  "theme_id": 12,
  "embedding": [0.031, -0.114, 0.072],
  "title": "미국, 대중국 AI 반도체 수출 규제 확대",
  "summary": "미국이 중국 대상 AI 반도체 수출 규제를 확대했다.",
  "published_at": "2026-09-03T03:35:24Z",
  "unclassified_at": "2026-09-03T04:10:01Z"
}
```

`theme_id`를 Kafka Key로 사용하여 같은 Theme의 메시지가 가능한 한 동일 Partition으로 전달되도록 한다.

---

# 미분류 기사 클러스터링 Trigger

`news.unclassified` 에 저장된 이벤트들을 집계해서 테마별로 개수를 확인했을 때, 50개가 넘을 때 클러스터링을 진행한다.
### 6-2. Spark(이슈 클러스터링용)
# 6-2. HDBSCAN 클러스터링

`news.unclassified` 에 저장된 이벤트들을 집계해서 동일한 테마에 해당하는 기사끼리, embedding을 대상으로 HDBSCAN을 실행한다.

---

# Cluster 형성 실패

형성에 실패한 기사들은 바로 삭제한다.

---

# 대표 기사 선정

신규 Issue의 이름과 설명을 생성하기 위해 Cluster 전체 기사를 LLM에 전달하지 않는다.

Cluster centroid와 가장 가까운 대표 기사 3건을 선택한다. (3건 미만일시 전체)

이렇게 하면 LLM 입력량을 줄이면서도 Cluster를 가장 잘 대표하는 기사들을 전달할 수 있다.

---

# LLM 기반 Issue 메타데이터 생성

### LLM 입력

```json
{
  "theme": "SEMICONDUCTOR",
  "articles": [
    {
      "article_id": "a-101",
      "title": "미국, 중국 대상 AI 반도체 수출 규제 확대",
      "summary": "미국 정부가 중국으로 수출되는 AI 반도체 규제를 강화했다."
    },
    {
      "article_id": "a-102",
      "title": "Washington tightens semiconductor export controls",
      "summary": "미국이 첨단 반도체에 대한 중국 수출 제한을 확대했다."
    },
    {
      "article_id": "a-103",
      "title": "New US rules target AI accelerators exported to China",
      "summary": "새로운 규제가 중국으로 수출되는 AI 가속기를 대상으로 한다."
    }
  ]
}
```

### LLM 출력

```json
{
  "name": "미국의 대중국 AI 반도체 수출 규제 확대",
  "summary": "미국 정부가 중국에 대한 첨단 AI 반도체 및 관련 장비의 수출 규제를 확대하면서 미중 기술 경쟁과 글로벌 반도체 시장에 영향을 주고 있는 이슈이다."
}
```

summary에 대한 임베딩값은, spark에서 계산한다.
## 7. Kafka(news.event)
# 7. 신규 Issue 생성 이벤트 발행

LLM을 통해 신규 Issue의 이름과 설명이 생성되면 카프카의 `news.event` 토픽에 `ISSUE_CREATE` 이벤트를 발행한다.

```json
{
  "event_id": "event-uuid-004",
  "event_type": "ISSUE_CREATE",
  "occurred_at": "2026-09-03T06:50:00Z",
  "payload": {
    "theme_id": 12,
    "name": "미국의 대중국 AI 반도체 수출 규제 확대",
    "centroid_embedding": [
      0.031,
      -0.114,
      0.072
    ],
    "article_ids": [
      "87fa2c9...",
      "31cd921...",
      "aac8210..."
    ],
    "first_seen_at": "2026-09-03T03:35:24Z",
    "last_seen_at": "2026-09-03T06:40:21Z"
  }
}
```

DB Writer는 해당 이벤트를 소비하여 신규 Issue를 생성하고 Cluster에 포함된 기사와 신규 Issue의 관계를 저장한다.

## 8. Database 저장

Spark에서 생성한 최종 이벤트는 `news.event` Kafka Topic으로 발행한다.

Database Writer는 `news.event`를 구독하고, `event_type`에 따라 PostgreSQL의 데이터를 생성하거나 갱신한다.

```text
Spark
  │
  ▼
news.event
  │
  ▼
Database Writer
  │
  ▼
PostgreSQL
```

Kafka 메시지의 `event_id`는 이벤트의 고유 식별자로 사용하며, 실제 DB 조회 및 갱신에는 `payload` 내부의 `article_id`, `issue_id` 등의 식별자를 사용한다.

---

### ARTICLE_ISSUE_ASSIGNED 처리

기존 Issue와 매칭된 기사에 대해서는 다음 이벤트가 전달된다.

```json
{
  "event_id": "event-uuid-002",
  "event_type": "ARTICLE_ISSUE_ASSIGNED",
  "occurred_at": "2026-09-03T06:40:02Z",
  "payload": {
    "article_id": "a-123",
    "issue_id": 102,
    "similarity": 0.94
  }
}
```

Database Writer는 `article_id`를 기준으로 해당 기사와 Issue의 관계를 저장한다.

예를 들어 기사 테이블에서 직접 Issue를 관리하는 경우 다음과 같이 처리할 수 있다.

```sql
UPDATE article
SET
    issue_id = 102,
    issue_similarity = 0.94,
    issue_assigned_at = NOW()
WHERE article_id = 'a-123';
```

별도의 관계 테이블을 사용하는 경우에는 다음과 같이 저장할 수 있다.

```sql
INSERT INTO article_issue (
    article_id,
    issue_id,
    similarity,
    assigned_at
)
VALUES (
    'a-123',
    102,
    0.94,
    NOW()
);
```

MVP에서는 하나의 기사가 하나의 Issue에만 속하도록 설계한다면 `article.issue_id`를 직접 갱신하는 방식이 더 단순하다.

---

### ISSUE_CREATE 처리

신규 Issue Candidate가 기존 Issue와 매칭되지 않은 경우 `ISSUE_CREATE` 이벤트가 전달된다.

```json
{
  "event_id": "event-uuid-004",
  "event_type": "ISSUE_CREATE",
  "occurred_at": "2026-09-03T06:50:00Z",
  "payload": {
    "theme_id": 12,
    "name": "미국의 대중국 AI 반도체 수출 규제 확대",
    "summary": "미국 정부가 중국에 대한 첨단 AI 반도체 수출 규제를 확대했다.",
    "centroid_embedding": [...],
    "article_ids": [
      "a-101",
      "a-102",
      "a-103"
    ],
    "first_seen_at": "2026-09-03T03:35:24Z",
    "last_seen_at": "2026-09-03T06:40:21Z"
  }
}
```

Database Writer는 하나의 Transaction 안에서 다음 작업을 처리한다.

```text
1. Issue 생성
2. 생성된 issue_id 조회
3. Cluster에 포함된 기사들의 issue_id 갱신
4. Transaction Commit
```

예를 들어 먼저 Issue를 생성한다.

```sql
INSERT INTO issue (
    theme_id,
    name,
    summary,
    centroid_embedding,
    status,
    first_seen_at,
    last_seen_at,
    created_at,
    updated_at
)
VALUES (
    12,
    '미국의 대중국 AI 반도체 수출 규제 확대',
    '미국 정부가 중국에 대한 첨단 AI 반도체 수출 규제를 확대했다.',
    :centroid_embedding,
    'ACTIVE',
    '2026-09-03T03:35:24Z',
    '2026-09-03T06:40:21Z',
    NOW(),
    NOW()
)
RETURNING id;
```

예를 들어 생성된 `issue_id`가 `205`라면 Cluster에 포함된 기사들을 해당 Issue에 연결한다.

```sql
UPDATE article
SET
    issue_id = 205,
    issue_assigned_at = NOW()
WHERE article_id IN (
    'a-101',
    'a-102',
    'a-103'
);
```

전체 작업은 하나의 Transaction으로 처리한다.

```text
BEGIN

Issue INSERT
        ↓
issue_id = 205
        ↓
Article a-101 → issue_id = 205
Article a-102 → issue_id = 205
Article a-103 → issue_id = 205

COMMIT
```

Issue 생성에는 성공했지만 기사 연결 과정에서 오류가 발생한 경우 전체 Transaction을 Rollback하여 Issue만 생성되는 불완전한 상태를 방지한다.

---

### Issue 정보 갱신

기존 Issue에 새로운 기사가 계속 연결되면 Issue의 상태 정보도 함께 갱신할 수 있다.

주요 갱신 대상은 다음과 같다.

```text
last_seen_at
centroid_embedding
updated_at
```

예를 들어 새로운 기사가 Issue 102에 연결된 경우:

```sql
UPDATE issue
SET
    centroid_embedding = :updated_centroid_embedding,
    last_seen_at = :published_at,
    updated_at = NOW()
WHERE id = 102;
```

`last_seen_at`은 해당 Issue에 속한 기사 중 가장 최근 기사 시각을 나타낸다.

`centroid_embedding`은 Issue에 새로운 기사가 추가됨에 따라 기존 centroid와 신규 기사 embedding을 반영하여 갱신한다.

---

### 이벤트 중복 처리

Kafka는 Consumer 장애나 재시작 상황에서 동일한 메시지가 다시 전달될 수 있기 때문에 Database Writer는 동일 이벤트가 여러 번 처리되어도 결과가 달라지지 않도록 멱등성을 보장해야 한다.

이를 위해 처리한 `event_id`를 별도로 저장한다.

예:

```text
processed_event
----------------------------
event_id        UUID PK
event_type
processed_at
```

Database Writer가 이벤트를 받으면 먼저 해당 `event_id`가 이미 처리되었는지 확인한다.

```sql
SELECT 1
FROM processed_event
WHERE event_id = 'event-uuid-002';
```

이미 존재하는 경우 해당 이벤트는 다시 처리하지 않는다.

처음 처리하는 이벤트라면 DB 작업과 함께 `event_id`를 저장한다.

```sql
INSERT INTO processed_event (
    event_id,
    event_type,
    processed_at
)
VALUES (
    'event-uuid-002',
    'ARTICLE_ISSUE_ASSIGNED',
    NOW()
);
```

이 작업 역시 실제 데이터 변경과 같은 Transaction 안에서 처리한다.

```text
BEGIN

event_id 중복 확인
        ↓
Article / Issue 데이터 변경
        ↓
processed_event INSERT
        ↓
COMMIT
```

이를 통해 Consumer 재처리 상황에서도 동일 Issue가 중복 생성되거나 동일 이벤트가 반복 적용되는 것을 방지한다.

---

### 최종 Database 저장 흐름

```text
                         news.event
                             │
                             ▼
                       Database Writer
                             │
                     event_type 확인
                             │
              ┌──────────────┴──────────────┐
              │                             │
 ARTICLE_ISSUE_ASSIGNED                ISSUE_CREATE
              │                             │
              ▼                             ▼
     article_id 조회                  Issue INSERT
              │                             │
              ▼                             ▼
      issue_id UPDATE                issue_id 반환
                                            │
                                            ▼
                                   article_ids UPDATE
              │                             │
              └──────────────┬──────────────┘
                             │
                             ▼
                   processed_event 저장
                             │
                             ▼
                          COMMIT
```

Database Writer는 Kafka와 PostgreSQL 사이의 저장 책임을 담당하며, Spark가 직접 PostgreSQL의 데이터를 생성하거나 수정하지 않도록 역할을 분리한다.


## 9. 이벤트 테이블 저장