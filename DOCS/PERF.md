# 집계 쿼리 성능 측정

`ThemeRepository` / `CountryRepository` 의 네이티브 집계 쿼리 5개에 대한 측정 기록.

- `findThemesByField`
- `findPopularThemesWithHourlyTrend`
- `findPopularThemes`
- `findOutgoingMentionRatios`
- `findIncomingMentionRatios`

> 아직 기록된 측정치가 없습니다. 아래 절차대로 측정한 뒤 [측정 기록](#측정-기록)
> 아래에 템플릿을 복사해 추가하십시오.

## 도구

| 항목 | 경로 |
|---|---|
| 대용량 데이터 생성 | `backend/scripts/perf/generate-bulk.sql` |
| 측정 세트 | `backend/scripts/perf/measure.sql` |
| 측정 환경 (설정 고정) | `backend/docker-compose.perf.yml` |
| 소량 개발용 시드 | `backend/scripts/seed/seed-dev.sql` |

```bash
docker compose -f backend/docker-compose.perf.yml up -d

psql -h localhost -p 15432 -U postgres -d witw -f backend/scripts/perf/generate-bulk.sql
psql -h localhost -p 15432 -U postgres -d witw -f backend/scripts/perf/measure.sql
```

## 규칙

**환경 블록을 반드시 함께 적습니다.** 절대 시간은 머신·설정마다 다르므로, 환경
정보가 없는 숫자는 나중에 해석할 수 없습니다.

**팀원과 비교할 때는 before/after 배수로 이야기합니다.** 머신이 달라도 배수는
대체로 옮겨집니다. 한쪽만 개선되면 그것 자체가 환경 의존적인 개선이라는 신호이므로
파고들 가치가 있습니다.

| 항목 | 방법 |
|---|---|
| 측정 환경 | `docker-compose.perf.yml` 로 통일. 로컬 설치본은 설정이 서로 달라 비교 불가 |
| 워밍 | 같은 파일을 3회 연속 실행하고 마지막 값을 기록. 첫 실행은 콜드 캐시 |
| 변경 단위 | 한 번에 하나만. 인덱스를 두 개 동시에 넣으면 원인 분리 불가 |
| 통계 | 인덱스 생성·데이터 변경 후 `ANALYZE` 필수 |
| 파라미터 | 쿼리 안에 리터럴로 박아야 함. 서브쿼리로 감싸면 플래너가 선택도를 추정하지 못해 플랜이 달라짐 |
| 쏠림 확인 | 지배 값과 롱테일 값 양쪽으로 측정. 한쪽만 재면 잘못된 결론이 나옴 |

`random_page_cost` 는 인덱스 채택 여부를 바꿉니다. 이 값이 다르면 실행 시간뿐
아니라 **플랜 자체가 달라지므로** 환경 블록에 반드시 남기십시오.

## 측정 기록

<!-- 아래 템플릿을 복사해서 최신 항목을 위에 추가하십시오. -->

---

## 템플릿

```markdown
## YYYY-MM-DD · <무엇을 바꿨는지>

### 환경
| 항목 | 값 |
|---|---|
| 실행 주체 | <이름> |
| 측정 환경 | docker-compose.perf.yml / 로컬 설치본 |
| PostgreSQL | |
| shared_buffers | |
| work_mem | |
| random_page_cost | |
| max_parallel_workers_per_gather | |

### 데이터
| 항목 | 값 |
|---|---|
| generate-bulk.sql 설정 | article_count / spread_hours / skew_exp |
| article 행 수 | |
| article 힙 크기 | |
| 24시간 윈도우 내 행 수 | |

### 변경
<적용한 인덱스 DDL 또는 쿼리 수정. 없으면 "없음 (베이스라인)">

### 결과 (Execution Time, ms · warm)
| 쿼리 | 파라미터 | before | after | 배수 |
|---|---|---|---|---|
| findThemesByField | - | | | |
| findPopularThemesWithHourlyTrend | | | | |
| findPopularThemes | | | | |
| findOutgoingMentionRatios | | | | |
| findIncomingMentionRatios | | | | |

### 관찰
<플랜에서 달라진 점>
- 스캔 방식 (Seq Scan / Index Scan / Index Only Scan / Bitmap)
- Buffers (shared hit vs read — 캐시 적중 여부)
- 추정 행 수 대비 실제 행 수 (괴리가 크면 통계 문제)
- Rows Removed by Filter
- Sort Method (external merge Disk 가 보이면 work_mem 부족)
```
