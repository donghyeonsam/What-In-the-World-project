# DB 성능 기준과 측정 기록

이 문서는 "이 쿼리가 빠른가 느린가"를 사람마다 다르게 판단하지 않도록 선을 긋는 것이 목적입니다.
측정 도구는 `scripts/perf/` 에 있고, 이 문서는 그 결과를 어떻게 해석하고 무엇을 채택할지를 정합니다.

---

## 1. 측정 환경 준비

성능 수치는 PostgreSQL 설정에 크게 좌우됩니다. 각자 로컬에 설치한 PostgreSQL 로 재면
`shared_buffers` 나 `random_page_cost` 가 달라서 숫자를 비교할 수 없습니다.
측정은 항상 `docker-compose.perf.yml` 컨테이너에서 합니다.

```powershell
# 1. perf 컨테이너 기동
docker compose -f docker-compose.perf.yml up -d

# 2. 스키마 적용
#    perf 컨테이너는 빈 Postgres 라서 Flyway 가 돈 적이 없습니다.
#    이 단계를 빼먹으면 generate-bulk.sql 이 TRUNCATE 에서 바로 실패합니다.
docker cp .\src\main\resources\db\migration witw-postgres-perf:/tmp/migration
# V1 → V2 → V3 → V4 → V5 → V6 → V6_1 → V7 → V8 순서로 적용
#   - 파일명 정렬은 V6_1 이 V6 보다 앞서므로 순서를 명시해야 합니다
#   - V6_1 은 LOCK TABLE 을 쓰므로 --single-transaction 이 필요합니다
#     (Flyway 는 각 마이그레이션을 트랜잭션으로 감싸주지만 psql -f 는 autocommit)

# 3. 스크립트 복사
docker cp .\scripts\perf\generate-bulk.sql witw-postgres-perf:/tmp/
docker cp .\scripts\perf\measure.sql      witw-postgres-perf:/tmp/
docker cp .\scripts\perf\write-test.sql   witw-postgres-perf:/tmp/

# 4. 데이터 생성 (article 50만 건, 약 1~2분)
docker exec witw-postgres-perf psql -U postgres -d witw -f /tmp/generate-bulk.sql

# 5. 측정 (3회 돌리고 마지막 결과 사용)
docker exec witw-postgres-perf psql -U postgres -d witw -f /tmp/measure.sql    > baseline.txt
docker exec witw-postgres-perf psql -U postgres -d witw -f /tmp/write-test.sql > baseline-write.txt
```

---

## 2. 기준은 4층

한 덩어리로 만들면 "느리다/빠르다" 말싸움이 됩니다. 층을 나누면 각 층이 독립적으로 판정됩니다.

```
0층  테이블 예산       "이 테이블에 인덱스를 몇 개까지 허용하는가"   ← 쓰기 패턴이 결정
1층  서비스 목표       "이 화면은 몇 ms 안에 떠야 하는가"
2층  쿼리 합격선       "이 쿼리는 통과인가 불합격인가"
3층  후보 채택 규칙    "예산 안에서 어느 후보가 이기는가"
```

0층이 자리를 배분하고, 3층에서 후보들이 그 자리를 놓고 경쟁합니다.
예산 편성과 사업 선정의 관계와 같습니다.

### 0층 — 테이블 예산

인덱스 비용은 **테이블 단위로 발생**합니다.
`article` 에 인덱스를 하나 추가하면 그 인덱스를 어느 쿼리가 쓰는지와 무관하게
`article` 로 들어오는 모든 INSERT 가 느려집니다.

그래서 "몇 개까지 허용할지"는 쿼리가 아니라 **그 테이블의 쓰기 패턴**이 정합니다.
이 층이 없으면 후보마다 개별적으로는 다 타당해 보이는데
합쳐놓으면 쓰기가 무너지는 상황을 잡지 못합니다.

| 테이블 | 규모 | 쓰기 패턴 | 예산 (PK 제외) |
|---|---|---|---|
| **article** | 계속 증가 | Kafka 컨슈머가 연속 INSERT (`DbWriterService.saveAll`) | **5** |
| **article_country_mention** | article × 2~3행 | article 갱신마다 `DELETE` 후 `INSERT` 로 **재작성** | **1** |
| issue | 200~ | `ON CONFLICT` upsert | 0 (PK + UK_ISSUE_NAME 으로 충분) |
| users | 적음 | 가입 시에만 | 현행 유지 (아래 참조) |
| country | 249 | 시드 후 없음 | **판정 스킵** |
| theme | 68 | 없음 | **판정 스킵** |
| field | 5 | 없음 | **판정 스킵** |

**총 가용 자리: article 5 + mention 1 = 6**

#### 작은 테이블은 판정 자체를 하지 않습니다

`field`(5행), `theme`(68행), `country`(249행)는 디스크 한두 페이지에 들어갑니다.
이 크기에서는 인덱스를 타는 것보다 순차 스캔이 빠르고, 플래너도 인덱스를 무시합니다.
만들어야 쓰기 비용과 혼란만 남습니다.

조인에 계속 등장하므로 쿼리 단위로 보면 후보로 보이지만, **측정 대상에서 빼는 것이 정답**입니다.
이건 테이블을 통으로 봐야 나오는 결론입니다.

#### article_country_mention 예산이 1인 이유

쿼리 단위로만 보면 인덱스가 필요한 쿼리가 C5 하나뿐이라 우선순위가 낮아 보입니다.
그런데 쓰기 패턴을 보면 (`DbWriterService`):

```java
"DELETE FROM article_country_mention WHERE article_id = ?"
"INSERT INTO article_country_mention (article_id, country_code) VALUES (?, ?)"
```

기사 하나를 갱신할 때마다 언급 행 2~3개가 **통째로 재작성**됩니다.
인덱스를 붙이면 그 재작성마다 인덱스도 갱신됩니다.
읽기 이득은 쿼리 1개인데 쓰기 비용은 article 쓰기량의 2~3배로 증폭됩니다.

이 비대칭은 테이블을 통으로 봐야 보입니다. 그래서 1개로 제한합니다.

#### users 는 이미 완비

`V6` 의 두 인덱스가 실제 쿼리와 정확히 맞습니다. 추가하지 마십시오.

| 인덱스 | 대응 쿼리 |
|---|---|
| `UK_USERS_EMAIL ON users (LOWER(email))` | `findByEmailIgnoreCase`, `existsByEmailIgnoreCase` |
| `UK_USERS_PROVIDER_ID ON users (auth_provider, provider_id) WHERE provider_id IS NOT NULL` | 소셜 로그인 |

#### 예산을 바꾸려면

쓰기 패턴이 바뀌었을 때만 바꿉니다. 읽기가 느리다는 이유로 늘리면 0층의 의미가 없어집니다.
바꿀 때는 근거(쓰기 빈도 변화, `write-test.sql` 수치)와 날짜를 남기십시오.

### 1층 — 서비스 목표 (화면 단위)

쿼리가 아니라 화면에서 시작합니다. 쿼리 하나가 30ms 여도 한 화면에서 5개 부르면 150ms 입니다.

| 화면 | 목표 (p95) | DB 예산 |
|---|---|---|
| 메인 대시보드 | 300ms | 150ms |
| 국가 상세 | 500ms | 250ms |
| 이슈 상세 | 500ms | 250ms |
| 로그인·인증 | 200ms | 50ms |

DB 예산을 전체의 절반으로 잡는 이유: 나머지는 네트워크, 직렬화, 프론트 렌더링이 씁니다.
DB 가 예산을 다 쓰면 나머지에서 무조건 초과합니다.

평균이 아니라 **p95** 로 잡습니다. 평균은 느린 요청을 숨깁니다.

> 위 숫자는 초안입니다. 팀에서 합의한 값으로 바꾸고, 바꾼 날짜를 남기십시오.

### 2층 — 쿼리 합격선

`EXPLAIN (ANALYZE, BUFFERS)` 출력에서 4개 지표만 봅니다.

| 지표 | 합격 | 경고 | 불합격 |
|---|---|---|---|
| **실행 시간** | 화면 예산의 1/3 이하 | 1/2 이하 | 초과 |
| **버려진 행 비율**<br>`Rows Removed by Filter` ÷ 읽은 행 | 50% 미만 | 50~90% | 90% 이상 |
| **디스크 정렬**<br>`Sort Method` | `quicksort Memory` | — | `external merge Disk` |
| **추정 오차**<br>추정 `rows=` vs `actual rows` | 10배 이내 | 10~100배 | 100배 초과 |

이 4개로 나누면 "느리다"의 원인이 자동으로 갈립니다.

- **버려진 행 비율**이 높다 → 인덱스 문제
- **디스크 정렬**이 뜬다 → `work_mem` 설정 문제 (인덱스로 해결 안 됨)
- **추정 오차**가 크다 → 통계 문제. `ANALYZE` 부족이거나 통계 타겟 문제.
  이 상태에서는 인덱스를 만들어도 플래너가 안 씁니다.

원인을 구분하지 않고 인덱스부터 넣으면, 설정 문제를 인덱스로 덮으려다 실패합니다.

#### 인덱스가 아니라 쿼리를 고쳐야 한다는 신호

플랜에서 **인덱스 스캔은 빠른데 힙 접근이 느리면** 쿼리 모양이 Index-Only Scan 을
막고 있는 것입니다. 인덱스를 더 만들어도 해결되지 않습니다.

```
Bitmap Index Scan    9.5ms   <- 인덱스는 제 일을 하고 있음
Bitmap Heap Scan   159.1ms   <- 여기가 병목. 힙을 14만 행 방문
```

이때 확인할 것: **집계가 참조하는 컬럼이 인덱스에 없어서** 힙을 봐야 하는가?
C1 이 정확히 이 경우였고, 집계를 서브쿼리로 분리해 `COUNT(*)` 로 바꾸니
`Index Only Scan` 이 잡히면서 16배 빨라졌습니다 (아래 6장 기록).

단, 쿼리 재작성은 **결과값이 달라질 위험**이 있으므로 반드시 원본과 출력을
비교 검증하십시오. 특히 LEFT JOIN 의 `COUNT(컬럼)` 을 `COUNT(*)` 로 바꾸면
매칭 없는 행이 0 이 아니라 1 로 세어집니다.

### 3층 — 후보 채택 규칙

이 프로젝트에서 가장 중요한 층입니다. **쓰기 부하** 때문입니다.

`DbWriterService.java` 의 Kafka 컨슈머가 `articleRepository.saveAll()` 로 기사를 계속 밀어넣습니다.
인덱스를 하나 추가할 때마다 이 INSERT 가 느려집니다.
읽기만 보고 인덱스를 늘리면 대시보드는 빨라지고 수집 파이프라인이 막힙니다.

**추가 조건 (전부 만족)**

1. 대상 쿼리가 실제 API 경로에 있다
2. 측정에서 **2배 이상** 개선 (1.3배는 노이즈와 구분 불가)
3. 개선 후 2층 합격선 통과
4. `write-test.sql` 저하 **10% 이내**

**거부 조건 (하나라도 해당)**

1. 기존 인덱스의 선행 컬럼과 중복
2. **0층 예산 초과** (article 5개, article_country_mention 1개). 예산이 찼으면 기존 것을 빼야 추가할 수 있습니다
3. **신규 인덱스 합계**가 힙 크기의 **30%** 초과 (PK 제외 — PK 는 예산 밖이므로 비율에서도 뺀다)
4. 측정 후 `pg_stat_user_indexes.idx_scan = 0` (한 번도 안 쓰임)

**설계 우선순위**

- `deleted_at IS NULL` **부분 인덱스**를 기본으로 합니다.
  모든 쿼리에 이 조건이 문자 그대로 있고, soft delete 가 약 2% 라 배제하면 크기와 선택도가 둘 다 좋아집니다.
- 복합 인덱스 컬럼 순서는 **등치 조건 먼저, 범위 조건 나중**입니다.
  B-tree 는 범위 조건을 만나는 순간 그 뒤 컬럼으로 탐색을 못 합니다.
- 범위 조건과 `ORDER BY` 가 다른 컬럼이면 **둘 중 하나만** 인덱스로 해결됩니다.

---

## 3. 쿼리 분류

Repository 네이티브 쿼리 21개를 성격별로 나눴습니다. `measure.sql` 의 섹션 구성과 같습니다.

### C. 시간 윈도우가 있는 쿼리 — 범위 인덱스 대상

24시간 구간만 읽으면 되므로 데이터가 쌓여도 읽는 양이 안 늘어납니다.
인덱스로 해결되는 부류입니다.

| # | 쿼리 | 등치 | 범위 |
|---|---|---|---|
| C1 | `ThemeRepository.findThemesByField` | theme_id (join) | published_at |
| C2 | `ThemeRepository.findPopularThemesWithHourlyTrend` | publisher_country_code | published_at |
| C3 | `ThemeRepository.findPopularThemes` | publisher_country_code | published_at |
| C4 | `CountryRepository.findOutgoingMentionRatios` | publisher_country_code | published_at |
| C5 | `CountryRepository.findIncomingMentionRatios` | mention.country_code | published_at |
| C6/C7 | `ArticleRepository.countArticlesLast24Hours` | (선택) country/issue | published_at |
| C8 | `ArticleRepository.getCountryRankByArticleCounts` | publisher_country_code | published_at |
| C9 | `ArticleRepository.findRepresentArticlesByCountry` | publisher_country_code | published_at |
| C10 | `IssueRepository.findGlobalIssueRankLast24Hours` | — | published_at |
| C11 | `IssueRepository.findCountryTonesLast24Hours` | issue_id | published_at |

#### 2026-09-14 — 시간 기준을 published_at 으로 통일

이전에는 `ArticleRepository` 만 `created_at` 을 썼습니다 (근거: FR-DSB-006 "수집" 기준).
아래 이유로 `published_at` 으로 통일했습니다.

**바꾼 이유**

`created_at` 은 행이 테이블에 들어온 시각입니다.
파이프라인 장애 후 밀린 기사를 한꺼번에 적재하면 그 시점에 수치가 몰려서,
실제로 일어나지 않은 급증으로 화면에 나타납니다.

**안전한 근거** — 수집기(`collection_kafka_producer_v2.py`)가 `published_at` 을 정규화합니다.

| 상황 | 처리 | `published_at_source` |
|---|---|---|
| 정상 추출 | 원문 값 사용 | `meta:*` / `jsonld:*` / `html:time` |
| 추출 실패 | **수집 시각으로 대체** | `collection_time_fallback` |
| 미래 시각 | **수집 시각으로 클램프** | `collection_time_future_guard` |

따라서 NULL 도 미래 값도 들어오지 않습니다.
추출 실패한 행은 `published_at == created_at` 이 되므로 어느 기준이든 결과가 같습니다.

**남은 확인 사항**

1. FR-DSB-006 원문은 여전히 "수집" 기준입니다. **요구사항 쪽 정합성을 기획과 확인할 것.**
2. 트레이드오프 — 3일 전 발행 기사를 오늘 수집하면 24시간 화면에 잡히지 않습니다.
   "수집했는데 안 보이는 기사"를 허용할지 판단이 필요합니다.
3. `countArticlesLast24Hours` 만 상한(`published_at < end_at`)이 없습니다. C8, C9 에는 있습니다.
   `created_at` 일 때는 미래 값이 불가능해 필요 없었으나 이제는 의미가 생겼습니다.
   수집기 future guard 에 의존하는 형태이므로 한 줄 추가를 권합니다.

**인덱스 영향** — 후보 G6 `(publisher_country_code, created_at)` 이 불필요해졌습니다.
C7·C8·C9 를 G1 이 커버하므로 `article` 후보가 6개에서 **5개**로 줄어 상한에 맞습니다.

### D. 정렬 + LIMIT 쿼리 — 정렬 서빙 인덱스 대상

시간 제한이 없지만 상위 N건만 필요합니다.
인덱스가 정렬 순서를 제공하면 N건만 읽고 멈출 수 있어, C 와 인덱스 모양이 다릅니다.

| # | 쿼리 | 등치 | 정렬 |
|---|---|---|---|
| D1 | `ArticleRepository.getRepresentArticlesByThemeId` | theme_id | theme_relevance_score DESC, id ASC |
| D2 | `...ByThemeIdAndCountryCode` | theme_id, country | 동일 |
| D3 | `ArticleRepository.getRepresentArticlesByIssueId` | issue_id | issue_similarity DESC NULLS LAST, id ASC |
| D4 | `...ByIssueIdAndCountryCode` | issue_id, country | 동일 |
| D5 | `IssueRepository.findCountryIssueDetail` | issue_id, country | EXISTS (조기 종료) |

### E. 전체 집계 쿼리

시간 제한도 LIMIT 도 없는 집계입니다.

**2026-09-14 측정으로 분류가 갈렸습니다.** 처음에는 4개 모두 "인덱스로 해결 불가"로 봤으나,
실제로는 **범위가 한정된 집계와 진짜 전체 집계는 완전히 다르게 동작합니다.**

| # | 쿼리 | 세는 범위 | 인덱스 효과 | 분류 |
|---|---|---|---|---|
| E1 | `ArticleRepository.countByDeletedAtIsNull` | **테이블 전체** | 1.35~1.50x | **반정규화 대상** |
| E2 | `IssueRepository.findIssueById` | 이슈 1건 | **9.9x** | 인덱스로 해결 |
| E3 | `IssueRepository.getIssuePreviewByIssueId` | 이슈 1건 | **56.9x** | 인덱스로 해결 |
| E4 | `IssueRepository.getPrimaryIssuesByThemeId` | 테마 1건 | **50.0x** | 인덱스로 해결 |

판별 기준은 "LIMIT 이 없다"가 아니라 **"WHERE 로 범위가 좁혀지는가"** 였습니다.
E2~E4 는 `WHERE i.id = ?` / `WHERE i.theme_id = ?` 로 범위가 한정되므로
`issue_id` 선행 인덱스가 해당 행만 찾아냅니다.

E1 만 조건이 `deleted_at IS NULL` 뿐이라 모든 행을 세야 합니다.
부분 인덱스가 힙보다 작아서 1.3~1.5x 는 빨라지지만 그 이상은 안 됩니다.
**`article_summary` 가 필요한 쿼리는 E1 하나입니다.**

### F. 참고 — 튜닝 대상 아님

| # | 쿼리 | 이유 |
|---|---|---|
| F1 | `IssueRepository.findIssueDetailsByIds` | issue PK 조회 + 작은 테이블 조인. article 안 건드림 |
| F2 | `UserRepository.findByEmailIgnoreCase` | `UK_USERS_EMAIL ON users (LOWER(email))` 함수 인덱스가 이미 정확히 맞음 |

---

## 4. 인덱스 후보

접근 패턴에서 기계적으로 도출한 것입니다. `measure.sql` G 섹션에 실행 가능한 형태로 있습니다.

| 후보 | 인덱스 | 대상 | 순위 |
|---|---|---|---|
| G1 | `article (publisher_country_code, published_at) WHERE deleted_at IS NULL` | C2, C3, C4 | 1 |
| G2 | `article (published_at, theme_id) WHERE deleted_at IS NULL` | C1 | 1 |
| G2-alt | `article (theme_id, published_at) WHERE deleted_at IS NULL` | C1 | 1 |
| G3 | `article_country_mention (country_code, article_id)` | C5 | 1 |
| G4 | `article (theme_id, theme_relevance_score DESC, id ASC) WHERE deleted_at IS NULL` | D1, D2 | 2 |
| G5 | `article (issue_id, issue_similarity DESC NULLS LAST, id ASC) WHERE deleted_at IS NULL` | D3, D4, D5 | 2 |
| ~~G6~~ | ~~`article (publisher_country_code, created_at)`~~ | — | **삭제** |
| G7 | `article (issue_id, published_at) WHERE deleted_at IS NULL` | C11, C10 부분 | 3 |

G6 은 시간 기준 통일로 삭제됐습니다 (위 3장 참조). C7·C8·C9 는 G1 이 커버합니다.

### 쿼리 → 후보 (역방향 조회)

측정 중에는 이 방향이 더 자주 필요합니다. "C1이 느린데 뭘 만들어야 하지?"

| 쿼리 | 주 후보 | 부수 효과 | 비고 |
|---|---|---|---|
| C1 `findThemesByField` | **G2** / **G2alt** | G1 1.71x, G7 1.62x | 후보 둘이 경쟁 — 컬럼 순서 두 버전 |
| C2 `findPopularThemesWithHourlyTrend` | **G1** | — | |
| C3 `findPopularThemes` | **G1** | — | |
| C4 `findOutgoingMentionRatios` | **G1** | — | 조합에서 0.82x 회귀 관찰됨 |
| C5 `findIncomingMentionRatios` | **G3** | — | mention 테이블 (article 예산과 별개) |
| C6 `countArticlesLast24Hours` (전체) | **G2** 3.92x | G1 2.69x | 국가 필터 없음 |
| C7 `countArticlesLast24Hours` (국가) | **G1** 9.93x | — | 단일 후보 최대 효과 |
| C8 `getCountryRankByArticleCounts` | **G2** 1.88x | G7 1.80x, G1 1.33x | |
| C9 `findRepresentArticlesByCountry` | **G1** | — | 범위와 정렬 컬럼이 달라 정렬은 못 태움 |
| C10 `findGlobalIssueRankLast24Hours` | **G7** 3.66x | — | |
| C11 `findCountryTonesLast24Hours` | **G7** 15.8x | G5 11.5x | |
| D1 `getRepresentArticlesByThemeId` | **G4** 529x | — | 정렬 서빙 |
| D2 `...ByThemeIdAndCountryCode` | **G4** 638x | — | 정렬 서빙 |
| D3 `getRepresentArticlesByIssueId` | **G5** 396x | G7 8.6x | 정렬 서빙 |
| D4 `...ByIssueIdAndCountryCode` | **G5** 601x | G7 13.3x | 정렬 서빙 |
| D5 `findCountryIssueDetail` | **G5** 20.1x | G7 13.9x | EXISTS 조기 종료 |
| E1 `countByDeletedAtIsNull` | **없음** | 어떤 인덱스든 1.3~1.5x | 반정규화 대상 |
| E2 `findIssueById` | **G5** 10.8x | G7 9.9x | issue_id 선행 부수 효과 |
| E3 `getIssuePreviewByIssueId` | **G5** 63.2x | G7 14.4x | issue_id 선행 부수 효과 |
| E4 `getPrimaryIssuesByThemeId` | **G7** 47.5x | G5 46.6x | |
| F1 `findIssueDetailsByIds` | 해당 없음 | — | article 안 건드림 |
| F2 `findByEmailIgnoreCase` | 해당 없음 | — | `UK_USERS_EMAIL` 이미 존재 |

배수는 2026-09-14 개별 측정값입니다. **"부수 효과" 열이 조합 설계의 핵심**입니다 —
주 후보가 없어도 다른 인덱스가 대신 커버하는 경우가 많아, 후보를 떨어뜨릴 때 여기를 봐야 합니다.

후보별 CREATE 문은 `measure.sql` G 섹션에 있습니다 (G1 663행, G2 673행, G2alt 680행,
G3 690행, G4 702행, G5 711행, G7 737행).


### 판단이 필요한 지점

**G2 vs G2-alt — 컬럼 순서**

C1 은 국가 필터가 없어서 24시간 구간 전체가 필요합니다.
`published_at` 선행이면 그 구간을 한 번에 훑고, `theme_id` 선행이면 테마 68개를 각각 탐색합니다.
어느 쪽이 유리한지는 논리로 정할 수 없습니다. **둘 다 재서 이긴 쪽만 남깁니다.**
동시에 두 개를 만들면 안 됩니다.

**G5 와 G7 — 선행 컬럼 중복**

둘 다 `issue_id` 로 시작하지만 두 번째 컬럼이 달라 별개 인덱스입니다.
G5 를 먼저 넣고 C11 이 충분히 빨라지면 G7 은 불필요할 수 있습니다. **반드시 G5 측정 후 판단합니다.**

**상한 여유가 없습니다**

`article` 후보가 G1, G2(또는 alt), G4, G5, G7 로 5개입니다.
3층 거부 조건의 상한과 정확히 같아서 **여유가 0입니다.**
시간 기준 통일 전에는 6개로 초과 상태였는데, G6 삭제로 겨우 맞춰진 것입니다.

따라서 새 인덱스가 하나라도 더 필요해지면 기존 것을 떨어뜨려야 합니다.
**전부 넣는 것이 목적이 아니라 재보고 걸러내는 것이 목적입니다.**
측정 후 효과가 작은 것부터 제거하고, 남은 자리를 기록해 두십시오.

### 기각된 후보 — 만들지 마십시오

| 후보 | 기각 사유 |
|---|---|
| `article_country_mention (article_id)` | PK 선행 컬럼이 이미 `article_id`. 완전 중복. 코드의 TODO 주석은 이 근거로 닫으면 됩니다 |
| `article (theme_id)` / `(issue_id)` / `(publisher_country_code)` 단독 | G1/G4/G5/G7 의 선행 컬럼에 포함됨. FK 라서 필요해 보이지만 불필요 |
| `article (deleted_at)` | 부분 인덱스 WHERE 절로 처리하는 편이 항상 나음. soft delete 2% 라 선택도도 나쁨 |

### 인덱스 튜닝 중 건드리면 안 되는 것

`findThemesByField` 의 `COUNT(a.id)` 를 `COUNT(*)` 로 바꾸면 **값이 틀립니다.**
LEFT JOIN 이라 매칭되는 기사가 없는 테마가 0 이 아니라 1 로 세어집니다.
`IssueRepository.java` 에도 같은 취지의 주석이 있습니다.
Index-Only Scan 을 노린다면 `COUNT(*)` 로 바꾸는 게 아니라 인덱스에 `INCLUDE (id)` 를 붙이십시오.

---

## 5. 반정규화 기준

인덱스 채택 기준과 별개입니다. 갱신 책임이 생기는 결정이라 더 빡빡해야 합니다.

**채택 조건 (전부 만족)**

1. 인덱스를 넣고도 화면 예산을 못 맞춘다
2. 누적량에 비례해 느려진다 (= 위 E 섹션에 있다)
3. **갱신 주체가 명확하다** — 누가 언제 이 집계값을 갱신하는가.
   후보: Kafka 컨슈머(`DbWriterService`) 또는 스케줄러
4. **최신성 허용치를 정했다** — "5분 지연 허용" 같은 합의.
   이게 없으면 실시간 정확성 요구가 붙어서 결국 원본 집계로 되돌아갑니다

3번과 4번 없이 반정규화하면 값이 틀어집니다.

### 이미 존재하는 반정규화 테이블

`V1__create_initial_schema.sql` 에 두 테이블이 있지만 **현재 아무 코드도 쓰지 않습니다.**

| 테이블 | 용도 | 현재 상태 |
|---|---|---|
| `article_summary` | `total_article_count`, `today_article_count` | Java 코드에서 언급 자체가 없음 |
| `country_tone` | 이슈×국가 톤 스냅샷 (`calculated_at` PK 포함) | 엔티티 없음. C11 이 매번 article 에서 직접 계산 |

즉 반정규화 논의는 새 설계가 아니라 **"이 두 테이블을 되살릴 것인가"** 입니다.

`country_tone` 의 PK 에 `calculated_at` 이 들어 있는 것으로 보아 원설계자는 주기적 스냅샷을 의도한 것으로 보이나,
주기가 얼마인지는 코드에 남아 있지 않습니다. 되살린다면 4번(최신성 허용치)을 여기서 정해야 합니다.

**되살리지 않기로 정했다면 마이그레이션에서 제거하십시오.**
`ddl-auto: validate` 로 바꾼 이상 스키마가 실제를 반영해야 하고,
안 쓰는 테이블이 남아 있으면 다음 사람이 "이건 뭐지" 하고 시간을 씁니다.

---

## 6. 측정 기록

### 기록 양식

절대 시간은 머신마다 다릅니다. **before/after 배수**로 이야기하십시오.

```markdown
## YYYY-MM-DD / <인덱스 이름 또는 변경 내용>

- 대상 쿼리: <measure.sql 섹션 번호와 메서드명>
- 데이터: generate-bulk.sql 기본값 (article 50만)
- 환경: measure.sql A 섹션 출력

| 지표 | before | after | 배수 |
|---|---|---|---|
| 실행 시간 | 000ms | 000ms | 0.0x |
| 버려진 행 | 00% | 00% | — |
| 플랜 | Seq Scan | Index Scan | — |

- 쓰기 영향: write-test.sql 000ms → 000ms (0.0x)
- 판정: 채택 / 보류 / 기각
- 근거:
```

---

### 2026-09-14 / 베이스라인 (인덱스 0개)

- 데이터: `generate-bulk.sql` 기본값 — article 50만 건(316MB), mention 113만 건(100MB)
- 국가 분포: A0 29.5%, A1 7.6%, 상위 10개국 63% (의도된 쏠림)
- 인덱스: `pk_article`, `pk_article_country_mention` **뿐**. `article` 에 보조 인덱스 0개
- 환경: `docker-compose.perf.yml` 고정값 (shared_buffers 256MB, work_mem 16MB,
  random_page_cost 1.1, max_parallel_workers_per_gather 2)

> 측정 범위: 당시 `measure.sql` 이 다루던 5개 쿼리만.
> `ArticleRepository` / `IssueRepository` 는 측정되지 않았습니다.
> 확장판으로 전체를 다시 잰 뒤 이 표를 갱신해야 합니다.

| # | 쿼리 | 실행시간 | 스캔 | 버려진 행 |
|---|---|---|---|---|
| C1 | `findThemesByField` | **253.2ms** | Seq Scan | 337,005 / 500,000 (67%) |
| C2 | `findPopularThemesWithHourlyTrend` | 110.5ms | Seq Scan | 356,344 (71%) |
| C3 | `findPopularThemes` | 59.0ms | Parallel Seq | ~451,911 (90%) |
| C4 | `findOutgoingMentionRatios` | 103.2ms | Parallel Seq | 91,105 + 128,365 |
| C5 | `findIncomingMentionRatios` | 110.0ms | Parallel Seq | 286,669 + 128,365 |

**2층 판정**

| 지표 | 결과 |
|---|---|
| 실행 시간 | ❌ C1 이 메인 대시보드 예산 150ms 초과 (253ms) |
| 버려진 행 | ⚠️ 67~90%, 전부 경고~불합격 구간 |
| 디스크 정렬 | ✅ 전부 `quicksort Memory`, 최대 112kB. `work_mem` 문제 아님 |
| 추정 오차 | ✅ 추정 163,556 vs 실제 162,995 (오차 0.3%). 통계 건강 |

**결론: 순수한 인덱스 문제.** 설정 문제도 통계 문제도 아님.

C1 이 가장 느린 이유는 명확합니다. 24시간 윈도우가 전체의 33% 만 남기는데
인덱스가 없어서 50만 건을 전부 읽고 33만 건을 버립니다.
`Buffers: shared hit=25280 read=13273` — 테이블 316MB 가 `shared_buffers` 256MB 보다 커서
디스크 I/O 가 발생합니다 (compose 주석대로 의도된 조건).

C3 의 59ms 는 착시입니다. 병렬 워커 3개를 쓴 결과이고 낭비율은 90% 로 가장 나쁩니다.
운영에서 동시 요청이 몰리면 워커 경합으로 이 수치는 유지되지 않습니다.

**쓰기 베이스라인**: 미측정 (`write-test.sql` 이 이 시점 이후에 추가됨)

---

### 2026-09-14 / article 인덱스 후보 측정

- 데이터: `generate-bulk.sql` 기본값 — article 50만 건(힙 307MB), mention 113만 건
- 환경: `docker-compose.perf.yml` 고정값
- 방법: 후보별로 생성 → `ANALYZE` → `measure.sql` 2회(1회차 워밍, 2회차 채택) → `write-test.sql` → 삭제
- 파라미터: `theme_id=1` (head, 119,646건 = 24%), `country='A0'` (29.5%), `issue_id=1`

#### 개별 후보 — 주요 개선 배수 (baseline / after)

| 쿼리 | baseline | G1 | G2 | G2alt | G4 | G5 | G7 |
|---|---|---|---|---|---|---|---|
| C1 findThemesByField | 259.9ms | **1.71** | 1.62 | 1.36 | 1.05 | 1.05 | 1.62 |
| C7 countArticles(국가) | 44.3ms | **9.93** | 0.65 | 0.90 | 1.04 | 0.98 | 1.02 |
| C8 getCountryRank | 248.7ms | 1.33 | **1.88** | 1.76 | 1.05 | 1.04 | 1.80 |
| C10 globalIssueRank | 74.0ms | 0.89 | 1.07 | 1.01 | 1.02 | 0.91 | **3.66** |
| C11 countryTones | 35.1ms | 0.84 | 0.55 | 1.05 | 1.08 | 11.51 | **15.83** |
| D1 representByTheme | 42.9ms | 0.86 | 1.08 | 0.61 | **529** | 1.02 | 1.05 |
| D3 representByIssue | 34.1ms | 0.86 | 1.07 | 1.07 | 1.02 | **396** | 8.57 |
| E3 issuePreview | 34.7ms | 1.00 | 1.07 | 1.08 | 1.08 | **63.2** | 14.4 |

정렬 서빙 인덱스(G4, G5)가 **수백 배**로 압도적입니다.
지금은 조건에 맞는 기사를 전부 읽어 정렬한 뒤 10건만 쓰는데,
인덱스가 정렬 순서를 제공하면 10건만 읽고 멈춥니다.

G1 은 D2/D4/D5 에서 **회귀**가 있었습니다 (0.66~0.37x).
`publisher_country_code` 선행이라 'A0'(29.5%) 구간을 크게 훑기 때문입니다.
이 회귀는 G5/G7 이 함께 있으면 사라집니다 — 플래너에 더 나은 선택지가 생기기 때문.
**개별 측정만으로 판단하면 안 되는 이유입니다.**

#### 조합 측정

| 조합 | 구성 | C~E 합계 | 배수 | 쓰기(5회 평균) | 신규 인덱스 크기 |
|---|---|---|---|---|---|
| baseline | — | 1493.1ms | 1.00 | 370.6ms | 0 |
| **S1** | G1+G2+G4+G5+G7 | **730.3ms** | **2.04** | 446.7ms (**+20.5%**) | 91MB (29.6%) |
| S2 | G1+G4+G5+G7 | 823.4ms | 1.81 | 411.3ms (+11.0%) | 79MB (25.8%) |
| S3 | G4+G5+G7 | 901.3ms | 1.66 | 395.5ms (+6.7%) | 64MB (20.8%) |
| S4 | G1+G4+G5 | 884.4ms | 1.69 | 399.7ms (+7.9%) | 64MB (20.8%) |

각 인덱스가 자기 슬롯 값을 하는지 확인:

- **G1** (S3→S2): C7 1.04→8.25, C2 0.85→1.64, C3 1.00→1.87 ✅
- **G7** (S4→S2): C10 0.92→3.39, C11 7.29→30.13 ✅
- **G2** (S2→S1): C1 1.50→1.80, C8 1.37→1.83 ✅

5개 모두 고유 기여가 있습니다. 겹쳐서 버릴 수 있는 후보는 없었습니다.

#### 판정 — **보류**

3층 거부 조건에 걸립니다.

| 조합 | 쓰기 저하 (기준 10%) | 크기 (기준 30%) | C1 예산 (150ms) |
|---|---|---|---|
| S1 | ❌ +20.5% | ✅ 29.6% | ❌ 중앙값 ~194ms |
| S2 | ❌ +11.0% | ✅ 25.8% | ❌ ~174ms |

**C1 은 어느 조합으로도 메인 대시보드 예산을 못 맞춥니다.**
배치 측정에서 144ms 가 나왔으나 단독 6회 재측정에서 152~204ms(중앙값 ~194ms)로,
앞선 쿼리들이 캐시를 데운 효과였습니다. **배치 안의 수치를 단독 성능으로 읽으면 안 됩니다.**

C1 병목은 인덱스가 아니라 힙 접근입니다:

```
Bitmap Index Scan on idx_article_published_theme   9.5ms   (141,002행 식별)
Bitmap Heap Scan on article                      159.1ms   (141,002행 힙 방문)
```

`INCLUDE (id)` 로 Index-Only Scan 을 유도해봤으나 플래너가 여전히 Bitmap 을 택했고,
중앙값 ~160ms 로 소폭 개선에 그쳤습니다 (인덱스 크기는 15MB 로 동일).
24시간 구간이 14만 행이라 무엇을 해도 그만큼은 만져야 합니다.

#### 결정이 필요한 사항

1. **쓰기 20% 저하를 받아들일 수 있는가** — Kafka 컨슈머의 현재 처리량 여유에 달렸습니다.
   운영에서 수집 속도와 컨슈머 랙을 확인해야 판단 가능합니다.
   여유가 충분하면 10% 규칙을 근거와 함께 완화하는 것이 합리적입니다 (읽기 2.04x 는 큰 이득).
2. **C1 을 어떻게 할 것인가** — 셋 중 하나입니다.
   - 메인 대시보드 예산을 300ms 로 올린다 (S1 이면 통과)
   - `findThemesByField` 를 사전 집계로 돌린다 (분야/테마별 24시간 카운트)
   - 화면에서 이 집계를 지연 로딩으로 뺀다
3. **E1 반정규화** — `article_summary` 되살리기. 인덱스로 1.35~1.50x 가 한계임이 확인됐습니다.

#### 쓰기 측정에 대한 주의

`write-test.sql` 은 1만 건 **대량 INSERT** 입니다.
Hibernate 의 `saveAll` 은 배치 설정이 없어 건별 INSERT 로 나가므로 형태가 다릅니다.
건별 경로는 왕복 비용 비중이 커서 인덱스 유지 비용의 상대적 비중이 더 낮을 수 있습니다.
운영 판단 전에 실제 컨슈머 처리량으로 확인하는 편이 안전합니다.

#### 재현 시 주의 (작업 중 발견)

`psql -c "DROP INDEX ...; VACUUM ...;"` 는 실패합니다.
psql 은 `-c` 의 여러 문장을 한 트랜잭션으로 묶는데 `VACUUM` 은 트랜잭션 안에서 못 돕니다.
VACUUM 이 실패하면서 앞의 DROP 까지 롤백됩니다. **`-c` 를 나눠서 실행하십시오.**

---

### 2026-09-14 / C1 쿼리 재작성 — 인덱스보다 효과가 큼

`findThemesByField` 는 인덱스만으로는 메인 대시보드 예산(150ms)을 못 맞췄습니다
(253ms → 160~194ms). 병목이 인덱스가 아니라 힙 접근이었기 때문입니다.

```
Bitmap Index Scan    9.5ms   (141,002행 식별)
Bitmap Heap Scan   159.1ms   (141,002행 힙 방문)   <- 여기
```

원인: `COUNT(a.id)` 가 `a.id` 를 참조하므로 인덱스만으로 끝낼 수 없어 힙을 봐야 합니다.
`COUNT(*)` 로 바꾸면 해결되지만 LEFT JOIN 이라 **값이 틀립니다**
(기사 없는 테마가 0 이 아니라 1 로 세어짐).

#### 해결 — 집계를 서브쿼리로 분리

article 집계를 먼저 끝내고 그 결과를 field/theme 에 붙입니다.
서브쿼리 안에서는 LEFT JOIN 이 아니므로 `COUNT(*)` 를 써도 안전하고,
`COALESCE(c.c, 0)` 으로 0건 테마를 복원합니다.

```sql
WITH bounds AS (SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul' AS end_at),
counts AS (
    SELECT a.theme_id, COUNT(*) AS c
    FROM article a CROSS JOIN bounds b
    WHERE a.deleted_at IS NULL
      AND a.published_at >= b.end_at - INTERVAL '24 hours'
      AND a.published_at <  b.end_at
    GROUP BY a.theme_id
)
SELECT f.id, f.name, t.id, t.name, COALESCE(c.c, 0) AS "articleCount24"
FROM field f
LEFT JOIN theme t  ON t.field_id = f.id
LEFT JOIN counts c ON c.theme_id = t.id
ORDER BY f.id, COALESCE(c.c, 0) DESC, t.id;
```

#### 측정

| | 원본 | 재작성 | 배수 |
|---|---|---|---|
| 인덱스 없음 | 245.4ms | 79.5ms | **3.1x** |
| G2 있음 | 222.1ms | **13.5ms** | **16.5x** |

원본 245.4ms → 재작성 + G2 13.5ms = **18.2x**. 예산 150ms 를 크게 통과합니다.

플랜이 `Bitmap Heap Scan` 에서 `Parallel Index Only Scan` 으로 바뀝니다.
집계가 `theme_id` 만 참조하므로 인덱스 `(published_at, theme_id)` 만으로 끝납니다.

#### 정합성 검증

원본과 재작성 결과를 `EXCEPT` 양방향으로 비교했습니다.

| 케이스 | 행 수 | 차집합 |
|---|---|---|
| 정상 (24시간, 모든 테마에 기사 있음) | 68 / 68 | 0 / 0 |
| 엣지 (1분 윈도우 + 기사 없는 테마 + 테마 없는 분야) | 70 / 70 | 0 / 0 |

엣지 케이스에서 0건 테마 70개와 `theme_id IS NULL` 행 1개가 양쪽 모두에 동일하게
나타났습니다. LEFT JOIN 의미가 보존됩니다.

#### 영향

- **C1 은 더 이상 사전 집계 대상이 아닙니다.** 앞선 기록의 "예산 상향 또는 사전 집계
  검토" 항목은 이 재작성으로 해소됩니다.
- **G2 가 필수에서 선택으로 바뀝니다.** 재작성만으로 79.5ms 라 이미 예산을 통과합니다.
  G2 를 빼면 article 인덱스가 4개가 되어 쓰기 저하(+20.5% → +11.0%)가 기준 안으로
  들어옵니다. 조합 판정 시 이 선택지를 포함해야 합니다.

#### 적용 전 확인

`ThemeRepository.findThemesByField` 를 고치는 코드 변경입니다.
기존 테스트(`FieldThemesRepositoryTest`)로 회귀를 확인하고,
0건 테마가 응답에 포함되는지 검증하는 케이스가 없다면 추가하십시오.


---

### 2026-09-14 / 최종 — C1 재작성 적용 + 인덱스 후보 확정

`ThemeRepository.findThemesByField` 재작성을 적용했습니다 (전체 테스트 87개 통과).
`measure.sql` C1 섹션과 `measure-table.sql` 도 새 원문으로 갱신했습니다.

| 구성 | C~E 합계 | C1 |
|---|---|---|
| 원본 + 인덱스 0개 (최초 baseline) | 1485.2ms | 252.7ms |
| 재작성 + 인덱스 0개 | 1265.3ms | 87.2ms |
| 재작성 + G1·G4·G5·G7 | 684.1ms | 91.5ms |
| **재작성 + G1·G2·G4·G5·G7** | **535.8ms** | **12.4ms** |

**최종 2.77x, C1 은 20.4x.**

#### 채택

| 후보 | 인덱스 | 근거 |
|---|---|---|
| G1 | `(publisher_country_code, published_at)` | C7 12x. 빠지면 C2 가 baseline 보다 느려짐(0.72x) |
| G2 | `(published_at, theme_id)` | 재작성 C1 에 7.4x. 원본 기준으로는 1.03x 였음 |
| G4 | `(theme_id, theme_relevance_score DESC, id)` | D1 424x, D2 379x |
| G5 | `(issue_id, issue_similarity DESC NULLS LAST, id)` | E3 69x, E4 55x, D3·D4 huge |
| G7 | `(issue_id, published_at)` | E4 49x, C11 21x, D5 20x |

전부 `WHERE deleted_at IS NULL` 부분 인덱스. article 예산 5칸을 채웁니다.

#### 기각

| 후보 | 사유 |
|---|---|
| G2alt `(theme_id, published_at)` | G2 에 패배. G2 없는 구성보다도 나쁨 |
| G3 `mention(country_code, article_id)` | 조합 기여 1.20x (2배 미달) + 크기 77.9% (30% 초과) |

#### 남은 결정 — 쓰기 +19.9%

C1 예산 문제는 재작성으로 해소됐고, 남은 미달 항목은 쓰기 하나입니다.
Kafka 컨슈머 처리량 여유를 운영에서 확인한 뒤 판단하십시오.
여유가 없으면 G2 를 빼고 4개로 가면 됩니다 (684.1ms, C1 91.5ms — 재작성 덕분에 예산은 통과).

마이그레이션(`V9__add_article_indexes.sql`)은 이 결정 후 작성합니다.
