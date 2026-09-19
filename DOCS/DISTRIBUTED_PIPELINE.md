# 분산처리 파이프라인 정리

![Pipeline v1](./image/pipeline_v1.png)

### 바로가기<hr>

- [1. 뉴스 수집기](#1-뉴스-수집기)
- [2. Kafka(news.raw.v1)](#2-kafkanewsrawv1)
- [3. NLP worker](#3-nlp-worker)
- [4. Kafka(news.enriched.v1)](#4-kafkanewsenriched)
- [5. Spark(기사 분석용)](#5-spark기사-분석용)
- [6. 이슈 매칭](#6-이슈-매칭)
  - [6-1. Kafka(news.unclassified.v1)](#6-1-kafkanewsunclassifiedv1)
  - [6-2. Spark(이슈 클러스터링용)](#6-2-spark이슈-클러스터링용)
- [7. Kafka(news.event.v1)](#7-kafkanewseventv1)
- [8. Database 저장](#8-database-저장)

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
```text
언론사
  │
  ├─ RSS 지원 ───────► RSS 기반 기사 탐색
  │
  └─ Sitemap 지원 ──► Sitemap 기반 기사 탐색
```

하나의 언론사가 여러 수집 Endpoint를 제공할 수 있으며, 수집기는 각 Endpoint를 기준으로 새로운 기사 URL을 탐색한다.

### 1-4. 수집 결과<hr>
새로운 기사가 발견되면 기사 본문과 함께 수집에 필요한 메타데이터를 생성한다.

수집 결과 예시는 다음과 같다.

```json
{
	"article_id":"SHA-256 방식의 고유 암호",
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
## 2. Kafka(news.raw.v1)
뉴스 수집기가 수집한 기사는 Kafka를 통해 다음 처리 단계로 전달한다.

Kafka는 각 처리 컴포넌트 사이에서 메시지를 전달하는 역할을 하며, 특정 Consumer의 처리 속도가 느려지더라도 Producer와 직접적으로 결합되지 않도록 한다.

```text
news.raw.v1
 │
 └──► NLP Worker
```

### 2-1. Topic 정보<hr>
| 항목 | 내용 |
| --- | --- |
| Topic | `news.raw.v1` |
| Producer | 뉴스 수집기 |
| Consumer | NLP Worker |
| Partition | 6 |

`news.raw`에는 기사 원문과 수집 단계에서 생성된 메타데이터가 저장된다.

## 3. NLP worker
NLP Worker는 Kafka의 news.raw.v1 토픽을 구독하여 기사 단위 NLP 처리를 수행한다.

처리가 완료되면 기존 기사 데이터에 nlp_worker_data를 추가한 뒤 다음 Kafka 토픽으로 전달한다.

### 3-1. NLP worker 주요 처리 내용<hr>
NLP Worker에서는 다음 작업을 수행한다.

- 국가 코드 정규화
- 언어 코드 정규화
- Domain 분류
- Theme 분류
- 기사 내 언급 국가 추출
- 감성 분석
- 기사 Embedding 생성
- NLP 처리 시각 및 버전 기록


### NLP worker 처리 결과<hr>
기존 수집 데이터는 그대로 유지하고, NLP 처리 결과는 nlp_worker_data 내부에 추가한다.

```json
{
  "article_id": "87fa2c9...",
  "source_id": "622913",
  "source_name": "Hankook Ilbo - South Korea (Korean)",
  "country": "South Korea",
  "article_url": "https://www.hankooki.com/news/articleView.html?idxno=342372",
  "published_at": "2026-09-01T08:15:03+00:00",
  "discovered_at": "2026-09-01T08:22:28.256121+00:00",
  "discovery_type": "SITEMAP",
  "endpoint_url": "https://www.hankooki.com/sitemap.xml",
  "success": true,
  "http_status": 200,
  "title": "국가철도공단, 정진혁 신임 이사장 취임…CEO 공백 종료",
  "body": "...",
  "body_length": 1036,
  "elapsed_ms": 87,
  "error": null,

  "nlp_worker_data": {
    "country_code": "KR",
    "language_code": "ko",
    "domain_id": 3,
    "theme_id": 27,
    "theme_relevance_score": 0.8123,

    "mentioned_countries": [
      {
        "country_code": "KR",
        "count": 3
      }
    ],

    "sentiment": {
      "label": "neutral",
      "score": 51.5,
      "confidence": 0.91
    },

    "article_embedding": [...],

    "processed_at": "2026-09-04T03:20:15+09:00",
    "version": "v1"
  }
}
```

`country_code`와 `mentioned_countries[].country_code`는 ISO 3166-1 alpha-2
대문자 두 글자(`KR`, `US`, `JP` 등)를 사용한다. `sentiment.score`는 0부터
100까지의 연속 논조 점수이며 Database의 `article.tone_score`에 저장한다.

## 4. Kafka(news.enriched.v1)
NLP Worker의 처리가 완료된 기사는 Kafka의 news.enriched.v1 토픽에 저장된다.

```text
news.enriched.v1
 │
 ├──► Spark
 │
 └──► HDFS 저장 처리(silver)
```

 ### 4-1. Topic 정보
 | 항목 | 내용 |
| --- | --- |
| Topic | `news.enriched.v1` |
| Producer | NLP worker |
| Consumer | Spark, HDFS 저장 처리 |
| Partition | 6 |

news.enriched.v1에는 기존 기사 원문 및 메타데이터와 함께 nlp_worker_data가 포함된 데이터가 저장된다.

이 토픽의 데이터는 이후 Spark에서 이슈 매칭, 통계 집계 등에 사용된다.

## 5. Spark(기사 분석용)
Spark는 Kafka의 news.enriched.v1 토픽을 구독하여 NLP 처리가 완료된 기사 데이터를 서비스에서 사용할 수 있는 형태로 가공한다.

Spark에서 처리된 데이터는 이후 두 개의 흐름으로 분기된다.

```text
news.enriched.v1
      │
      ▼
Spark(기사 분석용)
      │
      ├──► 7. Kafka(news.event.v1)
      │       └─ 기사 기본정보 1차 저장
      │
      └──► 6. 이슈 매칭
              └─ 기사와 기존 이슈 간 유사도 비교
```

### 주요 처리 내용
- news.enriched.v1에서 NLP 처리가 완료된 기사 수신
- Database 저장에 필요한 형태로 기사 데이터 가공
- 국가, 테마 등 기사 기반 통계 처리
- 기사 기본정보 저장을 위한 이벤트 생성
- 같은 Micro Batch에서 기사 Embedding과 Theme 정보를 사용해 기존 이슈 매칭

### 5-1. Kafka(news.event.v1)로 전달<hr>
Spark에서 가공이 완료된 기사 데이터는 우선 `news.event.v1` 토픽으로 전달한다.

이 단계의 목적은 이슈 매칭 결과와 관계없이 기사 자체를 먼저 Database에 저장하는 것이다.

```text
Spark
  │
  ▼
news.event.v1
  │
  ▼
Database(DB writer)
  │
  ▼
기사 기본정보 저장(물리적 저장)
```

이 시점에는 아직 이슈가 결정되지 않았으므로 `issue_id`,
`issue_similarity`, `issue_assigned_at`은 모두 `NULL`로 저장할 수 있다.

```text
article
 ├─ 기본 기사 정보 저장
 ├─ NLP 분석 결과 저장 
 ├─ issue_id = NULL 가능
 ├─ issue_similarity = NULL 가능
 └─ issue_assigned_at = NULL 가능
```

이후 이슈 매칭이 성공하면 별도의 이벤트를 통해 기존 기사에 issue_id를 추가한다.

Spark가 생성하는 최초 기사 저장 이벤트는 다음 계약을 사용한다. Kafka Key는
`article_id`이며, Database Writer도 `article_id`를 기준으로 upsert한다.

```json
{
  "event_type": "ARTICLE_UPSERT",
  "occurred_at": "2026-09-04T03:20:15+09:00",
  "payload": {
    "article_id": "87fa2c9...",
    "publisher_country_code": "KR",
    "theme_id": 27,
    "theme_relevance_score": 0.8123,
    "publisher": "Hankook Ilbo - South Korea (Korean)",
    "url": "https://www.hankooki.com/news/articleView.html?idxno=342372",
    "original_title": "국가철도공단, 정진혁 신임 이사장 취임…CEO 공백 종료",
    "crawled_at": "2026-09-01T08:22:28.256121+00:00",
    "embedding": [0.031, -0.114, 0.072],
    "tone_score": 51.5,
    "published_at": "2026-09-01T08:15:03+00:00",
    "mentioned_countries": [{"country_code": "KR", "count": 3}]
  }
}
```

`theme_relevance_score`는 NLP Worker가 선택한 Top-1 Theme와 기사 Embedding의
cosine similarity이며 범위는 -1부터 1이다. Spark는 NLP 계약에 없는 값을 임의로
생성하지 않는다. `published_at`을 포함한 필수 필드가 없거나 형식이 잘못된
메시지는 정합성 검사 실패로 처리한다.

### 5-2. 이슈 매칭 단계로 전달<hr>
동시에 Spark에서 처리된 기사는 6. 이슈 매칭 단계로 전달된다.

이 단계에서는 기사 Embedding과 기존 Issue Embedding을 비교하여 해당 기사가 기존 이슈에 포함될 수 있는지 판단한다.

```text
Spark
  │
  ▼
6. 이슈 매칭
  │
  ├── 매칭 성공
  │      └──► news.event.v1
  │             └─ 기존 기사에 issue_id 할당
  │
  └── 매칭 실패
         └──► news.unclassified.v1
```

즉, 5번 Spark 단계에서는 기사 자체의 저장 흐름과 이슈 분석 흐름을 분리한다.

```text
기사 기본정보
    └──► news.event.v1

기사 이슈 분석
    └──► 이슈 매칭
```

## 6. 이슈 매칭
Spark에서 기사 분석이 완료되면, 해당 기사가 기존에 생성된 이슈와 관련이 있는지 확인한다.

기사의 `article_embedding`과 기존 이슈의 `issue_embedding`을 비교하여 유사도를 계산하고, 기준값 이상이면 기존 이슈에 연결한다.

```text
Spark(기사 분석용)
        │
        ▼
6. 이슈 매칭
        │
        ├── 매칭 성공
        │      └──► news.event.v1
        │             └─ 기존 기사에 issue_id 할당
        │
        └── 매칭 실패
               └──► news.unclassified.v1
```
### 주요 처리 내용
- 기사 `article_embedding`과 기존 이슈의 `embedding` 비교
- 기사와 이슈 간 유사도 계산
- 기준값 이상이면 기존 이슈와 매칭
- 매칭 성공 시 해당 issue_id를 기사에 할당
- 매칭 실패 시 신규 이슈 후보로 분류

### 매칭 성공<hr>
기존 이슈와 충분히 유사한 경우 해당 이슈의 issue_id를 기사에 연결한다.

```text
기사
  │
  ▼
기존 이슈와 유사도 비교
  │
  ▼
매칭 성공
  │
  ▼
news.event.v1
  │
  ▼
기존 기사에 issue_id 할당
```

### 매칭 실패<hr>
기존 이슈와 충분히 유사한 이슈를 찾지 못한 경우 해당 기사는 신규 이슈 후보로 분류한다.

이후 `news.unclassified.v1` 토픽으로 전달되며, 미분류 기사들이 일정 수 이상 쌓이면 이슈 클러스터링 단계에서 새로운 이슈 생성에 사용된다.

```text
매칭 실패
   │
   ▼
news.unclassified.v1
   │
   ▼
Spark(이슈 클러스터링용)
```

## 데이터 입력

NLP 처리가 완료된 기사의 `nlp_worker_data`에는 이슈 매칭에 필요한
`theme_id`와 `article_embedding` 정보가 포함되어 있다. Spark는 앞 단계의 정합성
검사를 통과한 뒤 아래와 같은 내부 레코드로 사용한다.

```json
{
  "article_id": "a-123",
  "theme_id": 12,
  "embedding": [0.031, -0.114, 0.072],
  "title": "미국, 대중국 AI 반도체 수출 규제 확대",
  "summary": "미국 정부가 중국 대상 AI 반도체 수출 규제를 확대했다.",
  "published_at": "2026-09-03T03:35:24Z"
}
```

Spark Structured Streaming은 Kafka에 새로 유입된 기사들을 Micro Batch로 처리한다.

예를 들어 한 Micro Batch에 다음 테마의 기사들이 포함되어 있다고 가정한다.

```
SEMICONDUCTOR
AI
TRADE
```

---

## 기존 이슈 조회

새롭게 유입된 기사와 비교하기 위해 해당 기사들이 속한 Theme의 기존 이슈를 PostgreSQL에서 조회한다.
Issue 테이블은 `id`, `theme_id`, `name`, `embedding`, `first_seen_at`,
`created_at`, `updated_at`으로 구성한다. 별도의 상태나 최근 관측 시각 컬럼은
사용하지 않는다.

```sql
SELECT
    id AS issue_id,
    theme_id,
    embedding
FROM issue
WHERE theme_id IN (12, 15, 21)
  AND embedding IS NOT NULL;
```

Spark에서는 Micro Batch에 실제로 포함된 `theme_id`만 모아 JDBC로 후보 이슈를
조회한다. 운영 환경에서는 `issue` 테이블에 SELECT 권한만 가진 전용 계정을
사용한다.

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

Issue의 `embedding` TEXT 값은 JSON 숫자 배열로 변환한다. JSON 형식이 아니거나
숫자가 아닌 값이 포함된 기존 Issue는 해당 배치의 후보에서 제외한다. 최종적으로
다음과 같은 형태의 데이터를 얻는다.

```
+----------+----------+-----------------+
| issue_id | theme_id | issue_embedding |
+----------+----------+-----------------+
| 101      | 12       | [...]              |
| 102      | 12       | [...]              |
| 201      | 15       | [...]              |
+----------+----------+-----------------+
```

## 같은 Theme의 Issue끼리 후보 생성

기사와 모든 이슈를 비교하는 것이 아니라, 동일한 `theme_id`를 가진 이슈만 비교 대상으로 설정한다.

예를 들어 다음과 같은 형태가 된다.

```
+------------+----------+----------+------------------+-----------------+
| article_id | theme_id | issue_id | embedding        | issue_embedding |
+------------+----------+----------+------------------+-----------------+
| a-123      | 12       | 101      | [article...]     | [issue101...]      |
| a-123      | 12       | 102      | [article...]     | [issue102...]      |
| a-124      | 15       | 201      | [article...]     | [issue201...]      |
+------------+----------+----------+------------------+-----------------+
```

이를 통해 서로 다른 Theme에 속한 이슈와의 불필요한 유사도 계산을 방지한다.

---

## Cosine Similarity 계산

각 기사 embedding과 Issue의 `embedding` 사이의 Cosine Similarity를 계산한다.
Issue의 `embedding`은 해당 이슈에 속한 기사 임베딩의 centroid를 의미한다.

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

유사도가 기본 임계값 `0.93` 이상인지 판단해서 분기 처리한다. 운영 환경에서는
`ISSUE_MATCH_THRESHOLD`로 임계값을 조정할 수 있으며 기본값은 `0.93`이다.

```
similarity >= 0.93
    → 기존 Issue 매칭

similarity < 0.93
    → 미분류 기사
```

---

## Issue 매칭 성공

기존 Issue와 매칭된 경우 `ARTICLE_ISSUE_ASSIGNED` 이벤트를 생성한다.

```json
{
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

### 6-1. Kafka(news.unclassified.v1)
# 6-1. 미분류 기사 상태 저장

`news.unclassified.v1` Kafka에는 미분류 기사 발생 이벤트를 전달한다.

```
key = theme_id
```

```json
{
  "article_id": "a-123",
  "theme_id": 12,
  "embedding": [0.031, -0.114, 0.072],
  "title": "미국, 대중국 AI 반도체 수출 규제 확대",
  "summary": "미국 정부가 중국 대상 AI 반도체 수출 규제를 확대했다.",
  "published_at": "2026-09-03T03:35:24Z",
  "unclassified_at": "2026-09-03T04:10:01Z"
}
```

`theme_id`를 Kafka Key로 사용하여 같은 Theme의 메시지가 가능한 한 동일 Partition으로 전달되도록 한다.

---

# 미분류 기사 클러스터링 Trigger

`news.unclassified.v1`에 저장된 이벤트 중 발행 시각이 현재로부터 72시간 이내인
기사만 집계해서 테마별 개수가 50개 이상이면 클러스터링을 진행한다.

Spark 마이크로 배치가 50건보다 작더라도 메시지가 사라지지 않도록 검증된 미분류
기사는 `ISSUE_CLUSTER_STATE_LOCATION`의 Parquet 상태에 누적한다. `article_id`로
중복을 제거하며, 테마별 누적량이 MVP 고정 기준인 50건에 도달한 경우에만
해당 테마를 처리한다.

### 6-2. Spark(이슈 클러스터링용)
# 6-2. HDBSCAN 클러스터링

`news.unclassified.v1`에 저장된 이벤트 중 발행 시각이 현재로부터 72시간 이내인
기사만 집계해서 동일한 테마에 해당하는 기사끼리, embedding을 대상으로
HDBSCAN을 실행한다. 72시간이 지난 pending 기사는 trigger 집계와 상태 저장에서
제외한다.

MVP 고정값은 최소 군집 크기 4, `min_samples` 4이다. 테마 전체가 하나의 사건으로
강제 수렴하지 않도록 HDBSCAN의 단일 군집 허용 옵션은 끈다. HDBSCAN 군집 안에서도
개별 membership probability가 0.80 미만인 기사와 군집 centroid cosine similarity가
0.92 미만인 기사를 반복 제거한다. 제거 후 4건 미만인 군집은 생성하지 않는다.
한 번에 Driver로 가져오는 기사 수는 테마별 2,000건으로 제한하고, 초과분은 상태에
남겨 다음 실행에서 처리한다.

---

# Cluster 형성 실패

형성에 실패한 noise 기사와 개별 membership·centroid 응집도 기준을 통과하지 못한
기사는 발행 후 72시간까지 pending 상태에 남긴다. 후속 기사가 들어오면 같은 테마의
pending 기사와 다시 HDBSCAN을 실행한다. 새 기사가 들어오지 않은 테마를 매
마이크로 배치마다 반복 계산하지 않도록, 이번 배치에 새 기사가 들어온 테마만
재군집화한다. 실제 이슈 군집에 포함되어
`ISSUE_CREATE` 대상으로 확정된 기사만 pending 상태에서 제거하며, 72시간이 지난
미분류 기사는 만료 처리한다.

---

# 대표 기사 선정

신규 Issue의 이름과 설명을 생성하기 위해 Cluster 전체 기사를 LLM에 전달하지 않는다.

Cluster centroid와 가장 가까운 대표 기사 4건을 선택한다. (4건 미만일시 전체)

이렇게 하면 LLM 입력량을 줄이면서도 Cluster를 가장 잘 대표하는 기사들을 전달할 수 있다.

---

# LLM 기반 Issue 메타데이터 생성

### LLM 입력

```json
{
  "theme": "SEMICONDUCTOR",
  "cluster": {
    "article_count": 8,
    "hdbscan_membership_confidence": 0.87,
    "representative_articles": [
      {
        "title": "미국, 중국 대상 AI 반도체 수출 규제 확대",
        "summary": "미국 정부가 중국 대상 AI 반도체 수출 규제를 확대했다."
      },
      {
        "title": "워싱턴, 대중국 반도체 수출 통제 강화",
        "summary": "미국 정부가 AI 가속기와 관련 장비의 중국 수출 통제를 강화했다."
      }
    ]
  }
}
```

`article_id`는 LLM의 메타데이터 생성에 필요하지 않으므로 외부 요청에 포함하지 않는다.
Issue에 연결할 전체 `article_ids`와 최종 centroid 기준 기사별 cosine similarity는
Cluster 결과로부터 별도로 `ISSUE_CREATE` 이벤트에 넣는다.

### LLM 출력

```json
{
  "name": "미국의 대중국 AI 반도체 수출 규제 확대",
  "summary": "미국 정부가 중국에 대한 첨단 AI 반도체 및 관련 장비의 수출 규제를 확대했다."
}
```

`name`은 8~50자이며 구체적인 주체, 정책·사건·대상, 행동이나 결과가 드러나야
한다. `관련 이슈`, `최근 뉴스`, `동향`, `현황`, `전망`, `미래`, `발전`, `변화`,
`문제`, `논의`, `경쟁`처럼 구체적 사건을 식별할 수 없는 이름은 검증에서 거부하고
재시도한다. 대표 기사와 클러스터 정보를 바탕으로 이슈명을 생성하고, Spark는
클러스터 centroid를 Issue의 `embedding`으로 사용한다. LLM이 생성한 summary는
현재 Issue 테이블에 저장하지 않는다.

같은 Micro Batch에서 생성된 후보 중 정규화된 `name`과 `theme_id`가 모두 같은
후보는 하나로 병합한다. 이때 `article_ids`는 합집합으로 만들고, 병합된 전체 기사
embedding으로 centroid를 다시 계산한 뒤 `ISSUE_CREATE` 이벤트 하나만 발행한다.

## 7. Kafka(news.event.v1)
# 7. 신규 Issue 생성 이벤트 발행

LLM을 통해 신규 Issue의 이름이 생성되면 카프카의 `news.event.v1` 토픽에 `ISSUE_CREATE` 이벤트를 발행한다.

```json
{
  "event_type": "ISSUE_CREATE",
  "occurred_at": "2026-09-03T06:50:00Z",
  "payload": {
    "theme_id": 12,
    "name": "미국의 대중국 AI 반도체 수출 규제 확대",
    "embedding": [
      0.031,
      -0.114,
      0.072
    ],
    "article_ids": [
      "87fa2c9...",
      "31cd921...",
      "aac8210..."
    ],
    "article_similarities": {
      "87fa2c9...": 0.94,
      "31cd921...": 0.91,
      "aac8210...": 0.89
    },
    "first_seen_at": "2026-09-03T03:35:24Z"
  }
}
```

DB Writer는 해당 이벤트를 소비하여 신규 Issue를 생성하고 Cluster에 포함된 기사와
신규 Issue의 관계 및 centroid similarity를 저장한다.

## 8. Database 저장

Spark에서 생성한 최종 이벤트는 `news.event.v1` Kafka Topic으로 발행한다.

백엔드 Database Writer는 `news.event.v1`을 구독하고, `event_type`에 따라
PostgreSQL의 데이터를 생성하거나 갱신한다. Spark의 책임은 이벤트 발행까지이며
PostgreSQL을 직접 수정하지 않는다.

```text
Spark
  │
  ▼
news.event.v1
  │
  ▼
Database Writer
  │
  ▼
PostgreSQL
```

Kafka 메시지의 Key와 Database의 멱등 처리에는 `payload` 내부의
`article_id`, `article_ids`, `issue_id` 등 비즈니스 식별자를 사용한다.

---

### ARTICLE_UPSERT 처리

이슈 매칭 전 기사 기본정보를 먼저 저장한다. `article.id`에는
`payload.article_id`를 사용하고, 동일 ID가 이미 있으면 최신 NLP 결과로 갱신한다.
최초 저장 시 `issue_id`, `issue_similarity`, `issue_assigned_at`은 `NULL`이다.
`embedding` 배열은 현재 DB의 TEXT 컬럼에 JSON 문자열로 저장한다.

`mentioned_countries`는 기사를 저장한 뒤 `article_country_mention`에 upsert한다.
Database Writer는 기사와 언급 국가 저장을 하나의 Transaction으로 처리한다.

---

### ARTICLE_ISSUE_ASSIGNED 처리

기존 Issue와 매칭된 기사에 대해서는 다음 이벤트가 전달된다.

```json
{
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
WHERE id = 'a-123';
```

MVP에서는 하나의 기사가 하나의 Issue에만 속하므로 `article.issue_id`를 직접 갱신한다.

---

### ISSUE_CREATE 처리

신규 Issue Candidate가 기존 Issue와 매칭되지 않은 경우 `ISSUE_CREATE` 이벤트가 전달된다.

```json
{
  "event_type": "ISSUE_CREATE",
  "occurred_at": "2026-09-03T06:50:00Z",
  "payload": {
    "theme_id": 12,
    "name": "미국의 대중국 AI 반도체 수출 규제 확대",
    "embedding": [...],
    "article_ids": [
      "a-101",
      "a-102",
      "a-103"
    ],
    "article_similarities": {
      "a-101": 0.94,
      "a-102": 0.91,
      "a-103": 0.89
    },
    "first_seen_at": "2026-09-03T03:35:24Z"
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
    embedding,
    first_seen_at,
    created_at,
    updated_at
)
VALUES (
    12,
    '미국의 대중국 AI 반도체 수출 규제 확대',
    :embedding,
    '2026-09-03T03:35:24Z',
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
    issue_similarity = CASE id
        WHEN 'a-101' THEN 0.94
        WHEN 'a-102' THEN 0.91
        WHEN 'a-103' THEN 0.89
    END,
    issue_assigned_at = NOW()
WHERE id IN (
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
embedding
updated_at
```

예를 들어 새로운 기사가 Issue 102에 연결된 경우:

```sql
UPDATE issue
SET
    embedding = :updated_embedding,
    updated_at = NOW()
WHERE id = 102;
```

`embedding`은 Issue에 새로운 기사가 추가됨에 따라 기존 centroid와 신규 기사
embedding을 반영하여 갱신한다. 최초 등장 시각인 `first_seen_at`은 변경하지 않는다.

---

### 이벤트 중복 처리

Kafka는 Consumer 장애나 재시작 상황에서 동일한 메시지가 다시 전달될 수 있기 때문에 Database Writer는 동일 이벤트가 여러 번 처리되어도 결과가 달라지지 않도록 멱등성을 보장해야 한다.

`ARTICLE_UPSERT`는 `article_id` Primary Key를 기준으로 upsert하고,
`ARTICLE_ISSUE_ASSIGNED`는 `article_id`를 기준으로 update하므로 반복 처리해도
최종 상태가 같다.

`ISSUE_CREATE`는 Cluster의 `article_ids`를 잠근 뒤 이슈 할당 여부를 확인한다.
모든 기사가 미할당 상태일 때만 Issue를 생성하고, Issue 생성과 기사 연결을 같은
Transaction 안에서 처리한다.

```sql
BEGIN;

SELECT id, issue_id
FROM article
WHERE id IN ('a-101', 'a-102', 'a-103')
ORDER BY id
FOR UPDATE;

-- 모든 issue_id가 NULL인 경우에만 Issue 생성 및 기사 연결

COMMIT;
```

이미 같은 Issue에 할당된 기사들이라면 중복 이벤트로 판단하여 건너뛴다. 일부만
할당됐거나 서로 다른 Issue에 할당된 경우에는 충돌로 처리하고 자동 생성하지 않는다.

백엔드 Writer는 `ARTICLE_ISSUE_ASSIGNED` 처리 시에도 기사 행을 잠근 뒤 현재
`issue_id`가 `NULL`이거나 같은 이슈인 경우에만 반영해야 한다. 이미 다른 이슈가
붙은 기사는 후발 이벤트로 덮어쓰지 않고 충돌로 기록하며, Kafka offset은 DB
transaction commit 이후에만 commit해야 한다.

---

### 최종 Database 저장 흐름

```text
                         news.event.v1
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
                          COMMIT
```

Database Writer는 Kafka와 PostgreSQL 사이의 저장 책임을 담당하며, Spark가 직접 PostgreSQL의 데이터를 생성하거나 수정하지 않도록 역할을 분리한다.
