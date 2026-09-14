# Frontend Redesign Plan

작성일: 2026-09-14 · 기준: 현재 로컬 repository의 정적 코드 분석

요청 문서 `FRONTEND_REDESIGN_AUDIT_REQUEST.md`를 끝까지 읽고 작성했다. 소스·설정·DB·의존성은 변경하지 않았다. 이 문서만 신규 작성한다. 서버 실행, API 호출, DB 접속, 빌드·테스트·시드 실행은 하지 않았다. 따라서 아래의 ‘존재’는 코드/마이그레이션상 존재이며, 운영 배포 여부·실제 행 수·값 충전율·응답 속도는 **확인 필요**다. 첨부 ERD는 참고하되 최신 migration → entity → writer → repository → DTO → 프론트 소비 순서로 대조했다.

## 1. Executive Summary

개편의 중심은 **‘세계 이슈를 고르고, 같은 이슈를 보도한 국가와 기사를 한 화면에서 비교한다’**다. 이미 지구본과 패널이 나란히 있지만, 패널을 계층별로 계속 교체하고 국가 클릭이 이슈 맥락을 끊어 데이터 탐색 도구로서의 장점을 충분히 살리지 못한다.

우선순위는 다음과 같다.

1. **P0: 데이터 계약 복구.** 대표 기사 응답에 원문 URL이 없고 번역 제목만 내려온다. writer는 원제만 저장하며 번역 제목·요약은 채우지 않는다. UTC 저장과 KST 조회/해석도 불일치한다. 시각화보다 먼저 해결해야 한다.
2. **P0: 탐색 평탄화.** 국가·분야·테마를 필터로, 이슈를 작업 맥락으로 취급한다. 분야/테마 전체/기사 더보기 때문에 별도 화면 스택을 쌓지 않는다.
3. **P0: 지구본과 비교 패널 연결.** 이슈 선택 후 국가 클릭은 같은 이슈의 국가별 기사로 이어진다. 전체 국가 논조는 유지하고 선택국만 강조한다.
4. **P0: 읽기 중심 반응형 화면.** 이슈 헤드라인, 국가 비교 행, 시간별 기사량, 기사 목록을 서로 다른 시각 형식으로 배치한다. 모바일의 1280px 최소폭을 해소한다.
5. **P0/P1: 인증 기반을 완성한 뒤 관심사·저장을 도입.** 회원가입·로그인 등 6개 API와 users 테이블은 이미 있다. 그러나 프론트 인증, 현재 사용자 조회, 보호된 개인화 API/테이블은 없다.

기능 등급은 문서 전체에서 다음 의미로 사용한다.

| 등급 | 의미 |
|---|---|
| A | 현 조회 API/데이터로 프론트 작업 가능. 기존 API의 기간·상한·품질 한계를 그대로 따른다 |
| B | 기존 DB 데이터의 조회·응답·인증 API 보완으로 가능. 신규 영속 데이터가 필수는 아니다 |
| C | DB schema 또는 데이터 생성·저장 파이프라인 변경까지 필요 |

**A는 이미 화면에 구현되었다는 뜻이 아니다.** 성능 최적화 인덱스 추가는 B 기능의 별도 측정 결과에 따라 판단한다. 각 제안의 P0/P1/P2, 가치·난이도, Backend/DB 지원은 15장의 기능 ID 표를 따른다.

## 2. 현재 서비스/데이터 구조 이해

### 2.1 조사 범위와 근거

| 영역 | 확인한 파일/경로 | 판단에 사용한 내용 |
|---|---|---|
| 요청 | [감사 요청](./FRONTEND_REDESIGN_AUDIT_REQUEST.md) | 요구 범위, 17개 목차, 변경 금지 |
| 프론트 진입/화면 | [App.jsx](../frontend/src/App.jsx), [main.jsx](../frontend/src/main.jsx), [navigation.js](../frontend/src/navigation.js) | 실제 화면 8종, 내부 history, 미사용 이전 navigation |
| 데이터 연결 | [api.js](../frontend/src/data/api.js), [responseAdapters.js](../frontend/src/data/responseAdapters.js), [useResource.js](../frontend/src/data/useResource.js) | 조회 7개, 데이터 변환, 오류/갱신 |
| UI | [components](../frontend/src/components), [styles](../frontend/src/styles), [countries.js](../frontend/src/data/countries.js) | 지구본 이벤트, 필터, 목록, 고정폭, 5개국 |
| 실행 설정 | [package.json](../frontend/package.json), package-lock.json, vite.config.js, frontend/nginx/default.conf | React/Vite/Three, 동일 출처 API 프록시 |
| 백엔드 | [domain](../backend/src/main/java/com/ssafy/witw/domain) 하위 entity/dao/service/controller/dto | SQL 범위·정렬·집계·응답·인증 |
| DB | [migration](../backend/src/main/resources/db/migration) V1~V8 및 V6_1 | 최신 관계·nullable·삭제 컬럼·회원·국가 시드 |
| 저장 경로 | [DbWriterService.java](../backend/src/main/java/com/ssafy/witw/infra/kafka/dbwriter/DbWriterService.java), 이벤트 DTO | 실제 필드 충전, UTC, 언급 중복 제거 |
| 데이터 처리 | bigdata/collector/registry.csv, nlp-worker/pipeline, spark/apps/article_event.py·issue_matching.py·issue_clustering.py·gms_issue_generator.py, ml/config.yaml | 수집국/품질 메타, 논조 fallback, 군집/요약의 저장 여부 |
| 기획/설명 | README.md, frontend/README.md·DECISIONS.md, DOCS/ERD.md·API명세서.md·planning.md·요구사항 명세서.md·DISTRIBUTED_PIPELINE.md·PERF.md, sql-files | 계획과 코드의 차이, 성능 실측 부재 |
| 검증/배포 기반 | frontend/tests, backend/src/test, backend/build.gradle·application*.yml, .gitlab-ci.yml, infra/nginx | 테스트 범위, 세션·CORS, 배포 경계 |

전체 디렉터리와 관련 파일을 검색한 뒤 사용자 기능과 데이터 경로를 중심으로 읽었다. 모델 가중치·tar 아카이브·모든 수집 매체 원문을 전수 조사한 것은 아니다. 저장소에서 AGENTS.md는 발견하지 못했다. 기존 `front-sub/`는 작업 시작 시부터 untracked였고 요청 문서가 있었다.

### 2.2 관계: 단순 4단 트리로만 취급하면 안 된다

```text
field 1 ─ N theme 1 ─ N issue
              │            │
              └─ N article ┘  (article.issue_id는 NULL 가능)
country 1 ─ N article.publisher_country_code
article N ─ M country          (article_country_mention)
issue + country + calculated_at ─ country_tone
article_summary                (집계용 별도 테이블)
users                          (뉴스와의 관심/저장 관계 없음)
```

article은 theme를 직접 참조하므로 **이슈가 아직 없는 기사도 테마에서 발견할 수 있어야 한다.** DB FK는 각각의 참조만 보장한다. article.theme_id와 연결된 issue.theme_id가 같은지는 별도 정합성 점검 대상이다.

| 테이블 | 실제 구조/역할 | UI 함의 |
|---|---|---|
| field | id, code, name, description | 분야는 큰 필터. 독립 상세 페이지의 정보는 부족 |
| theme | field_id, name, description, TEXT embedding | 분야별 탐색, 설명, 테마별 기사/이슈 묶음 |
| issue | theme_id, name, first_seen_at, embedding, 생성/수정 시각 | 이슈 비교의 중심. 설명/summary 컬럼은 없음 |
| article | 문자열 ID, 발행국, theme, nullable issue, URL, 원제/번역제, summary, 관련도/유사도/논조, 여러 시각, deleted_at | 출처 연결·분류 전 기사·기간 검색에 사용 가능 |
| country | ISO alpha-2 PK, 한/영 이름, 위경도 | 발행국과 언급국을 별도 개념으로 표시 |
| article_country_mention | (article_id, country_code) 복합 PK | 기사당 해당 국가가 언급됐는지. 등장 횟수는 저장하지 않음 |
| country_tone | (calculated_at, issue_id, country_code) PK, 평균/표준편차/기사 수 | schema 존재. 현재 조회는 이 테이블 대신 article에서 직접 계산 |
| article_summary | 누적/오늘 수/updated_at | schema 존재. 현재 서비스는 직접 count하며 이 테이블을 읽지 않음 |
| users | email, password_hash, auth_provider, provider_id, role, created_at, withdrawn_at | 기본 계정만 존재. 관심 국가/테마/이슈·북마크·열람 이력 없음 |

마이그레이션 대조 결과: V2/V3에서 기사 ID가 VARCHAR(255)로 바뀌고 UUID가 제거됐다. V4는 국가 좌표, V5는 이슈 할당 필드 nullable, V6는 users, V6_1은 동명이슈 병합, V7은 이름 unique 및 **article.embedding 삭제**, V8은 전 세계 국가 마스터 보강이다. 첨부 ERD의 기사 embedding과 DOCS의 theme.domain_id는 최신 구현과 다르다. 실제 FK는 theme.field_id다. DB 마이그레이션 적용 이력은 접속하지 않아 확인하지 못했다.

### 2.3 데이터가 생성되는 범위

수집 → Kafka → NLP(국가 언급/테마/논조/embedding) → Spark 기사 이벤트 및 이슈 매칭·군집 → Kafka DB writer → PostgreSQL → 조회 API → 프론트다. HDFS 원자료나 ML 학습 메타가 있다고 곧바로 사용자용 API 데이터가 되는 것은 아니다.

- `DbWriterService`는 URL·원제·발행/수집 시각·테마 관련도·논조를 저장한다. **translated_title/summary setter는 호출하지 않는다.** 새 기사 제목은 조회 SQL에서 번역 제목만 선택하므로 ‘제목 없음’이 될 수 있다.
- GMS가 이슈 name과 summary를 만들지만 `build_issue_events`는 summary를 이벤트에 넣지 않는다. issue에도 summary 컬럼이 없다. ‘이슈 한 줄 설명’은 C다.
- `first_seen_at`은 생성 군집 내 가장 이른 **발행 시각**이고 동명 이슈 upsert 때 더 이른 값으로 합쳐진다. 실제 사건 발생 시각/모든 국가로의 확산 시각이 아니다.
- 언급 payload의 count는 검증 후 버리고 국가 코드를 집합으로 저장한다. 현재 ‘국가 관심도’는 반복 단어 횟수나 사용자 관심도가 아니다.
- 논조 모델은 비활성/로드 실패 시 50.0 fallback이 가능한 코드다. model 정보는 최종 article에 저장되지 않으므로 ‘중립’과 ‘분석 fallback’을 DB에서 분리할 수 없다.
- `country_tone` 정기 snapshot writer와 `article_summary` 갱신 작업은 현재 실행 코드에서 확인되지 않는다. 테이블 존재만으로 과거 추이 데이터가 쌓였다고 판단하지 않는다.

### 2.4 시간·통계의 실제 의미

| 표시/데이터 | 실제 쿼리 기준 | 주의 |
|---|---|---|
| 전체 수집 기사 | deleted_at IS NULL count | 삭제되지 않은 현재 저장 기사 수. 영구 누적 수집 총량과 다를 수 있음 |
| recent24ArticleCount / todayArticleCount | created_at 최근 24시간 | 자정 이후 아님. crawled_at도 아님 |
| 국가 순위 | created_at 최근 24시간, 전체 country 포함 | 수집 기사량 순위이며 국가 중요도 아님. 0건 국가도 공동 순위 |
| 글로벌 TOP5 / 국가 인기 테마 / 논조 / 언급 비율 | published_at 최근 24시간 | 수집 KPI와 다른 모집단 |
| 테마 시간별 추이 | 다음 정각을 끝으로 한 24개 1시간 버킷 | 현재 미완료 시간 포함. 국가 홈의 rolling 24h와 정확히 같지 않음 |
| 이슈 총 기사/보도 국가, 테마 주요 이슈 | 전체 기간 | 최근 24시간 순위/논조와 섞어 해석하면 안 됨 |
| 테마/이슈 대표 기사 | 전체 기간, 관련도/유사도 순, 최대 10 | 최신순/전체 검색 결과 아님 |
| 국가 대표 기사 | created_at 최근 24시간, 관련도 순, 3개 | ‘논조별 보기’도 이 3개를 프론트 필터하는 것 |

**P0 시간 정합성(F01):** writer는 UTC를 timezone 없는 LocalDateTime으로 저장하지만 repository는 `NOW() AT TIME ZONE 'Asia/Seoul'`로 경계를 만들고 프론트는 offset 없는 문자열에 `+09:00`을 붙인다. 현재 경로로 저장된 행에는 9시간 기준 불일치가 생길 수 있다. 기존 행의 시간 규약은 확인 필요다. UTC 저장/쿼리 경계/offset 포함 응답을 합의하고, 기존 데이터가 혼재하면 보정 작업을 별도로 설계해야 한다. 과거 데이터를 무조건 9시간 이동시키지 않는다.

## 3. 현재 프론트 구조 및 화면 목록

실제 앱은 `frontend/`에 있고 `front-sub/`는 분석 문서 위치다. package.json은 React `^18.3.1`, Vite `^5.4.11`, Three `^0.128.0`을 선언하고 package-lock.json의 확정 버전은 React/React DOM **18.3.1**, Vite **5.4.21**, Three **0.128.0**이다. router·전역 상태·차트·컴포넌트 패키지는 없다. React state/props, fetch, CSS Modules/tokens, 직접 구현한 Three 지구본·HTML/CSS 그래프를 쓴다. 백엔드 build.gradle은 Java 21, Spring Boot 4.1.1, JPA/PostgreSQL/Flyway, Redis Session/Security/Mail/Kafka 구성을 선언한다. 이는 저장소 설정 확인이며 설치/실행 성공 검증은 아니다.

### 3.1 route의 실체

URL에 대응되는 router 등록은 없다. `App.jsx`의 `history: [HOME]`와 마지막 view.type으로 8가지 화면을 렌더한다. `go()`는 대시보드만 스택 초기화하고 기사→기사만 마지막 항목을 교체한다. 그 밖의 이동은 누적한다. 브라우저 Back/새로고침/링크 공유와 이 스택은 연결돼 있지 않다.

`navigation.js`, `data/model.js`, `data/adapters.js`, `DashExplore`, 구형 `ToneScatter`는 현재 App에서 사용하지 않는 목업 경로다. `IssueHero`, `ToneLegend`도 App에 연결되지 않는다. README/DECISIONS의 더블클릭·7개국·목업 수집 카운터·분류 breadcrumb 설명을 현 동작으로 오인하면 안 된다. 현재 지구본은 **한 번 클릭으로 국가 화면**을 연다.

### 3.2 화면별 감사

아래 D는 홈 D0에서 진입 동선 기준의 내부 화면 전환 깊이다. 한 URL이어도 실제 작업 깊이는 증가한다.

| view | 목적/주요 컴포넌트 | API·현재 데이터 | 대표 D | 중복/제거 가능한 단계·상태 문제 |
|---|---|---|---:|---|
| dash | PanelHeading, KpiCards, IssueCardList | global/issues: 수집 수·TOP5 | 0 | KPI+리스트 중심. 분야/전체 테마 직행 입구 없음. 새 이슈 시각 미사용 |
| country | CountryIdentity, ThemeCardList, AttentionList, ArticlePreviewList | countries/{code}: KPI, TOP3 테마, outgoing TOP4, 기사3 | 1 | incoming은 별도 attention에서만. 주요 ‘이슈’는 응답 자체에 없음 |
| themes | SubHeading, ThemeDetailList | 국가 popular?limit=10 | 2 | 분야별 그룹에서 또 field로 이동. ‘전체 보기’는 전체 테마가 아니라 TOP10 |
| field | ThemeDetailList | 동일 popular 결과에서 fieldName 필터 | 3 | themes와 같은 데이터. 탭/필터로 충분. global 분기는 있으나 일반 UI 직행 없음 |
| theme | ThemeIssueList, ArticleFeed | theme overview: 설명, 글로벌 이슈10, 대표 기사10 중3 | 2~4 | 국가 맥락이어도 주요 이슈는 글로벌 전체 기간. 기사 더보기는 같은 응답 재표시 |
| issue | KpiCards, ApiToneScatter, ArticleFeed | global detail + issue overview 병렬, 기사10 중3 | 1~5 | 국가 경유면 논조 전체를 1개국으로 잘라 비교 약화. 더보기는 별도 화면 |
| attention | AttentionPanel 방향 토글 | country의 sourceMentions/targetMentions 재사용 | 2 | 국가 패널 안 탭으로 합칠 수 있음. 방향별 TOP4만 존재 |
| articles | ThemeFilterPanel, ArticleFilterBar, ArticleFeed | 국가/테마/이슈 응답 재사용, 논조는 로컬 필터 | 2~6 | 별도 기사 검색 API/상세 route/페이지네이션 없음. theme 변경 시 issueId를 제거함 |

공통 상태: `ResourceState`에 loading/error/retry가 있고 일부 목록은 Empty를 쓴다. 실패 시 목업 수치를 채우지 않는 점은 유지한다. 다만 이슈 두 요청 중 하나가 실패하면 Promise.all 전체가 실패하며, 갱신 실패도 기존 내용을 숨긴다. 국가/이슈/테마 데이터는 자동 주기 갱신하지 않고 dashboard만 60초 polling한다. ‘10분마다 갱신’ 안내는 현재 조회 구현에서 근거가 확인되지 않는다.

기사 목록의 기본 empty 안내 ‘논조 필터를 변경’은 분석 미완료·기사 없음에도 적용된다. fields 실패와 기사 실패를 분리해야 한다. 테마/이슈 기사의 ‘전 세계’ 부제는 countryCode가 있어도 고정되어 실제 요청 범위와 충돌한다.

반응형: `.shell { min-width:1280px }`, 56:44 grid와 최소 660/520px, 패널 내부 스크롤 구조다. 모바일은 가로 스크롤이 사실상 강제된다. CSS 하단에서 본문/제목 크기를 보강했으므로 초기 8~11px 규칙만 보고 모든 화면이 작은 글씨라고 판단하지 않는다. 그래도 고정폭/스크롤·검색 focus trap/복귀·캔버스 키보드 조작·WebGL 실패 대체는 개선 대상이다.

## 4. 현재 UX/UI 문제

가장 큰 문제 5개는 다음과 같다.

1. **탐색 스택이 깊고 위치가 보존되지 않는다.** 동일한 국가/테마 선택을 반복해도 history가 늘고, 직접 URL·브라우저 Back이 없다. 홈에서 분야 탐색도 우회해야 한다. (F03)
2. **지구본이 이슈 비교 맥락을 이어주지 못한다.** 이슈를 보다가 국가를 누르면 국가 대시보드로 바뀐다. 논조 행 클릭은 카메라만 움직인다. 국가 경유 이슈는 다른 국가 데이터를 숨긴다. 이미 논조 채색이 있으므로 ‘순수 장식’은 아니지만 비교 작업의 중심은 아니다. (F04)
3. **화면 구성은 반복되는데 핵심 읽기 데이터는 연결되지 않는다.** KPI/테마/이슈/기사 목록의 반복과 별도 더보기 대신 세계 분포·비교·시간 변화가 전면에 필요하다. 현재 기사 URL/요약 누락과 원제 fallback 부재는 읽기의 종착점을 막는다. (F02, F05)
4. **숫자·논조의 의미와 데이터 품질이 일관되지 않는다.** UTC/KST, 수집/발행/전체기간, TOP10/전체, 표본 부족 처리 차이가 있다. 지구본은 minSample=null이고 패널은 30건 미만 평균 배지만 숨겨 트랙/tooltip에는 값이 남는다. (F01, F04, F06)
5. **모바일과 회원 이용의 구조가 준비되지 않았다.** 데스크톱 고정폭이며 인증 버튼·세션 복원·개인화 저장이 없다. 가입 후 무엇을 다시 찾아오는지 정의하지 않으면 로그인만 추가된 서비스가 된다. (F05, F11~F13)

추가 관찰: 로고 링크는 preventDefault만 하여 홈 이동이 아니다. 국가 검색은 전달된 한글 이름만 검색하므로 영문 검색 기획과 다르다. TOP5에서 themeName으로 ID를 역추적하며 catalog 로딩에 의존한다. 대표 기사 필터의 앞 5개 테마도 전 세계 인기 TOP5가 아니라 field 순서로 평탄화한 앞부분이다.

## 5. Navigation Depth 분석

### 5.1 측정 규칙

홈을 D0로 두고 독립 화면을 계속 여는 단계를 센다. 클릭 수 I는 버튼/행 선택 횟수이며 텍스트 입력·스크롤은 제외하고 따로 적는다. 패널·모달을 겹쳐 여는 것도 작업 깊이에 포함한다. 기존 앱의 최단 경로와 긴 실제 가능 경로를 나누며, 미구현 목적지는 임의의 숫자로 ‘가능’ 처리하지 않는다.

```text
현재 홈
 ├─ 이슈 → 대표 기사 화면
 └─ 국가 → 인기 테마 전체 → 분야 → 테마 → 이슈 → 대표 기사 화면
      ├─ 테마 → 대표 기사 화면
      ├─ 국가 관심도 → 방향 토글
      └─ 대표 기사 화면 → 테마 찾기 → 분야 필터 → 테마 선택
```

| 작업 | 현재 클릭/깊이 | 개편 클릭/깊이 목표 | 제한 |
|---|---|---|---|
| 특정 국가 주요 뉴스 | 지구본 국가 1I/D1, 검색 열기+국가 2I/D1 (+검색 입력) | 국가 선택 1I/D1 | 기존은 대표 기사3/테마3. 국가 주요 이슈 추가는 B(F08) |
| 특정 이슈 상세 | 홈 TOP5 1I/D1; 국가→전체→분야→테마→이슈 5I/D5 | 홈 이슈 1I/D1, 테마 결과에서 이슈 선택까지 통상 2~3I/D1 | TOP5 밖 모든 이슈 검색은 B(F09) |
| 분야→테마→기사 | 국가→전체→분야→테마의 기사3: 4I/D4; 더보기까지 5I/D5 | 홈에서 분야 선택→테마 선택으로 기사 즉시 2I/D1 | Explore 메뉴로 먼저 들어가면 3I. 전수 기사 조회는 B |
| 같은 이슈의 국가별 기사 비교 | 완성된 비교 UI 없음. 이슈 화면 1I 뒤 국가 행 1I는 시점만 변경. 지구본 국가 클릭은 맥락 이탈 | 홈 이슈→국가 선택 2I/D1로 ‘전체 vs 선택국’; 두 국가 직접 지정은 3I/D1 | 두 나라 모두 직접 고르는 일을 2I라 주장하지 않음. 제목/매체 비교 A, 원문 B |
| 기사 상세/원문 | 상세 route 없음. API URL 부재로 외부 원문도 현재 계약상 막힘 | 노출 기사 클릭 1I로 D2 상세; 홈→이슈→기사 2I/D2, 원문 +1I | 직접 기사 상세는 B(F02). DB에 본문은 없음 |
| 로그인 후 관심 콘텐츠 | 인증 UI/개인화 미구현, 측정 불가 | 로그인 완료 후 원래 화면 복원 0I, ‘내 뉴스’ 1I/D1 | 폼 입력/인증 전체를 1I로 세지 않음. 관심 데이터 C |

반복 이동으로 현재 history가 임의로 길어질 수 있으므로 D6을 시스템 최대 깊이라고 보지 않는다. 개편은 탐색 workspace D0 → 맥락 패널 D1 → 기사 상세 D2를 기본으로 하고 로그인 overlay까지 겹치지 않게 교체하여 D3 이내로 제한한다.

## 6. ERD/Backend에 존재하지만 프론트에서 활용하지 않는 데이터

### 6.1 현재 조회 API 계약 전수 대조

경로 prefix는 `/api/v1`. 아래 조회 7개는 모두 frontend/api.js가 호출한다. 즉 ‘아예 안 쓰는 뉴스 조회 API’보다 **필드 미소비·범위 제한·DB에서 DTO로 누락**이 더 큰 문제다.

| API | 실제 응답·제약 | 프론트 소비/누락 |
|---|---|---|
| GET /global/issues | 누적/24h 수집 수, globalIssues TOP5, firstSeenAt | 시각 제외 대부분 사용. country/theme 필터 없음 |
| GET /global/issues/{id} | issueInfo(전체 기간 기사/국가 수), countryTones(24h, 좌표/평균/최소/최대/SD/n) | KPI/논조 사용. 좌표 대신 정적 5개국 사용 |
| GET /issues/{id}/overview | issuePreview, 동일 countryTones, representArticles. articleLimit 1~10, countryCode는 기사에만 적용 | detail과 중복 논조 조회. 국가별 기사 API는 있으나 비교 UI 없음 |
| GET /countries/{code} | countryName, todayArticleCount, rank, popularThemes3, 양방향 mentions4, articles3 | incoming은 추가 단계. 국가 주요 이슈/분야 전수 분포 없음 |
| GET /countries/{code}/themes/popular | limit 1~10, fieldName, count24, 24개 시간 버킷 | 추이 이미 사용. ‘숨은 신규 데이터’로 분류하면 안 됨 |
| GET /themes/{id}/overview | 설명, 주요 이슈 ID/제목, 기사 최대10. countryCode는 기사만 | 주요 이슈는 국가/24h 필터 안 됨. 기사3 우선/더보기10 |
| GET /themes/by-field | fieldId/name, themeId/name/articleCount24; 0건 포함 | 선택 catalog로 소비. 전역 분야 합계·분포는 미사용 |

모든 `RepresentArticle`은 articleId/articleTitle/articleTone/articlePublisher/publishedAt **5개 필드뿐**이다. 프론트가 읽는 url/summary는 실제 응답에 없다. SQL projection도 그 필드를 선택하지 않는다. 반환 envelope는 BaseResponse의 status/message/data 계열이며 프론트는 data를 꺼낸다. 읽기 helper는 GET 전용이다.

### 6.2 데이터별 활용 가능성

| 데이터 | 현재 지원/사용 상태 | 새 사용자 가치 | 등급·ID |
|---|---|---|---|
| globalIssues.firstSeenAt | API 있음, 화면 미사용 | ‘수집된 관련 기사 중 최초 발행’ 배지. 사건 발생/급상승으로 표현 금지 | A F07, 시간 정합성 선행 |
| by-field의 articleCount24 | catalog에 포함, 분야 요약 미사용 | 세계 분야별 보도 비중·테마 선택을 홈에 노출 | A F07. 같은 범위 합계만 분모로 사용 |
| 국가별 평균/범위/SD/n | 이미 사용하나 카메라 연결에 그침 | 동일 이슈의 국가별 논조+대표 기사 비교 | A F04. 분포 히스토그램 자체는 아님 |
| countryTones 좌표 | API 제공, 정적 위치 사용 | 응답 국가 포인트 위치 반영 | A F04. 추가 국가 polygon/검색 전수는 B F10 |
| incoming/outgoing mentionRatio | 기존 attention에서 사용 | 국가 패널 양방향 토글·선택국 연결선 | A F07(5개국 내); 전수 좌표/건수는 B F10 |
| article.url/original_title | DB/writer 있음, DTO 누락 | 원문 이동·번역이 없어도 제목 표시 | B F02 |
| article.summary/translated_title | 컬럼 있음, 현재 writer 충전 없음 | 요약/번역을 보장한 기사 읽기 | C F14. 기존 채워진 행 노출만은 B이나 가용성 미확인 |
| theme_relevance_score/issue_similarity | DB와 정렬에 사용, 수치 미노출 | ‘테마 관련도순/이슈 유사도순’ 설명, 관련 기사 | 기존 정렬 설명 A F06, 새 전수 조회 B F09. 신뢰도 점수 아님 |
| published_at/crawled_at/created_at/assigned_at | 일부만 API 제공 | 기간 탐색·수집 지연·미분류 상태 | B F09/F06. 실제 시간 규약 검증 선행 |
| 국가×테마/분야×기사 | 기존 관계 있음, 전수 집계 API 없음 | 국가별 분야 분포, 국가 주요 이슈 | B F08. TOP10을 전체 분포로 재정규화 금지 |
| 기사×issue×publisher_country×published_at | DB 있음 | 국가별 최초 관련 보도·시간별 보도량 | B F15. 전파 인과·사건 확산을 입증하지 않음 |
| country_tone / article_summary | 테이블만 확인, 현재 서비스 미사용 | 검증된 snapshot/집계 기반 추이 | C F16. 운영 적재가 확인되면 일부 조회는 B로 재평가 |
| theme/issue.embedding | TEXT 저장, 대중 API 없음 | 관련 이슈 추천 후보 계산 | B 후보지만 품질/성능 검증 필요. 이번 1차 범위 제외(F17) |
| article.embedding | V7에서 삭제 | 기사 간 의미 유사도 검색 | C F17. 동일 이슈 내 기사 묶음 B와 구별 |
| 수집 registry quality/source metadata | 파일에 존재, article의 publisher와 정규화 FK 없음 | 수집 범위·출처 다양성 설명 | 상세 자동 연결은 C F16. 기사 신뢰도 인증으로 사용 금지 |

언급 비율은 해당 방향의 **기사-국가 쌍 수 합계**를 분모로 하며 자기 국가는 제외한다. 한 기사에 여러 나라가 있으면 여러 쌍이 된다. TOP4 합계가 100%가 아닐 수 있고 ‘한국 기사 중 미국을 언급한 기사 비율’과는 다르다. ‘국가 간 보도 언급 비중’으로 명명하고 계산식을 제공한다.

## 7. 신규 회원 기능 도입 시 활용 가능한 기능

### 7.1 현재 구현과 빈 부분

AuthController에는 signup, login, logout, exists, email/send, email/verify가 구현되어 있다. 가입은 이메일 인증 확인 후 BCrypt 비밀번호 저장이며 로그인은 기존 세션 무효화 후 `userId`를 새 세션에 저장한다. Redis 이메일 코드는 7자리 영숫자, 유효 300초, 이메일별 시간당 발송5회/검증5회 제한, 인증 성공 상태30분이다. 이메일/Redis의 실제 운영 연결은 확인하지 않았다.

가입/로그인 요청의 비밀번호 검증은 현재 8~72자다. 인증 성공 응답 중 Void 응답은 `BaseResponse`의 NON_NULL 정책으로 data 키가 생략된다. 현재 프론트 request는 data 키가 없으면 실패로 처리하므로 POST 기능만 추가해서는 충분하지 않다. 인증 성공 envelope와 조회 envelope를 모두 처리하는 응답 계약 보완이 필요하다(F11). 인증 완료 상태는 이메일별 Redis 키로 저장되며 브라우저 세션에 묶이지 않는다. 인증 증명의 가입 요청 바인딩도 회원 출시 전 검토 대상이다.

반면 `/users/me` 또는 이에 준하는 세션 상태 조회, 비밀번호 재설정, 탈퇴 controller, SSAFY 인증 처리는 찾지 못했다. users에 provider enum/withdrawn_at이 있다고 기능 완료가 아니다. Spring Security는 anyRequest permitAll, `/api/v1/**` CSRF 제외이며 세션 userId와 보호 API의 인가 연결도 추가 구현 필요다. 설정에 HttpOnly/SameSite=Lax가 있지만 profile에 secure:false가 있다. 회원 쓰기 기능을 내기 전에 인증·인가·쿠키·CSRF를 실제 배포 프록시 환경과 함께 검증해야 한다(F11).

### 7.2 가입 전후 UX

비회원은 세계/국가/테마/이슈/기사 열람·비교를 그대로 이용한다. 저장을 누르면 로그인 화면을 열고 기존 issue/country/filter 및 저장 의도를 유지한다. 가입 완료는 자동 로그인으로 가정하지 않는다. 현재 signup은 세션을 발급하지 않으므로 로그인 단계를 명시한다.

```text
열람/저장 시도 → 로그인 또는 회원가입
회원가입: 이메일 입력 → 코드 전송/확인 → 비밀번호 설정 → 가입 완료 → 로그인
로그인 성공 → (선택적 관심 국가/테마 설정, 건너뛰기) → 원래 맥락 복귀
헤더 ‘내 뉴스’ → 관심 이슈/저장 기사/관심사 편집
```

서버의 현재 사용자 확인을 먼저 거치고, 초기 상태는 ‘세션 확인 중’으로 표현한다. 새로고침 때 임의로 비회원 표시했다가 프로필로 바꾸지 않는다. 세션 만료 시 열람은 유지하고 저장만 재로그인을 요구한다.

| 회원 기능 | 현실적인 범위 | 필요 작업 | 단계 |
|---|---|---|---|
| 관심 국가·분야·테마 | 관심 국가는 발행국 기준, 분야 선택 시 하위 테마 포함 규칙 | 관계 테이블/조회·수정 API | C F12, P1 |
| 관심 이슈/저장 이슈 | 같은 관계로 통합해 중복 개념 제거 | user_issue_follow, follow/unfollow | C F12, P1 |
| 기사 북마크 | ID 기반 서버 저장, 삭제 기사 표시 | user_article_bookmark, 목록 API | C F12, P1 |
| 최근 본 기사 | 필요 시에만 동기화, 일단 필수 범위 제외 | user_article_history와 보관/삭제 규칙 | C F13, P2 |
| 개인화 뉴스 필터 | 국가·테마·이슈 조건 저장 | 관계/설정 저장 + B 기사 검색 기반 | C F12, P1 |
| 개인화 홈 | ‘내 관심 이슈의 여러 국가 보도’와 ‘관심 테마 기사’ | 선호 데이터·조회 API, 규칙 기반 순위 | C F12, P1 |
| 알림/추적 | 팔로우 이슈의 새 보도 알림 | 이벤트 기준·중복 방지·발송 채널·읽음 상태 | C F13, P2 |

개인화는 관심 국가 기사만 가두기보다 **관심 이슈에 대한 다른 나라 보도도 함께** 보여주는 방향이 서비스 정체성과 맞는다. 행동 추천 모델 없이 명시적 관심사 기반부터 시작한다. 브라우저 localStorage 시제품을 서버 개인화 완료로 부르지 않는다.

## 8. 지구본 활용 개편안

### 8.1 두 모드로 역할을 분명하게 한다(F04, F07~F10)

**세계 탐색 모드:** 지도 국가를 선택하면 오른쪽 국가 패널/모바일 sheet를 갱신한다. 기존 API로 기사3·테마3·언급 비중을 즉시 노출한다. ‘국가 주요 이슈’는 API 추가 후 넣고 그전에는 글로벌 이슈를 국가 이슈로 꾸미지 않는다.

**이슈 비교 모드:** 이슈를 고르면 모든 응답 국가의 논조가 보이고 국가 행에 n·평균·편차가 표시된다. 국가를 누르면 issueId를 유지한 채 국가별 대표 기사 요청을 보낸다. 지도 채색을 선택국 한 개로 자르지 않는다. 국가 행 클릭과 지도 클릭의 결과를 같게 맞춘다. 2개국 비교는 최대 2열, 나머지는 전환 가능한 국가 행으로 제공한다.

```text
홈 이슈 클릭
 → issue 상세/overview 요청 → 세계 논조 + 대표 기사 표시
 → 국가 클릭 → issueId 유지 + compareCountry 변경
 → /issues/{id}/overview?countryCode=KR&articleLimit=10
 → 동일 패널의 기사 영역 변경, 국가 전체 논조 유지
 → 다른 국가 추가 → 두 국가 기사/표본 비교
 → 기사 선택 → 읽기 패널 (B 완료 후), 닫으면 같은 이슈/국가로 복귀
```

국가 분석 자체로 이동하는 별도 명시적 버튼은 두되 기본 국가 클릭이 이슈를 해제하지 않게 한다. 세계 모드 복귀 시 issueId와 compareCountry만 해제하고 사용자가 선택한 분야/테마 조건은 URL 정책에 맞춰 유지한다.

### 8.2 그래픽 원칙

- 논조는 색, 보도량은 숫자/점 크기 중 한 가지, 선택은 외곽선으로 구분한다. 범례·기간·모집단을 지도 상단에 고정한다(F06).
- n이 작을 때 평균 숨김 또는 참고값 노출 정책을 지도/패널/tooltip 모두 동일하게 적용한다. 30은 현 프론트 기준일 뿐 통계적 보증이 아니다(F04).
- 국가 언급은 선택한 방향의 상위 연결만 표시한다. 5개국 밖 언급은 목록에 남기고 좌표 API 없이 임의 위치를 만들지 않는다(F07/F10).
- 지구본 기사량 표현은 현재 응답 범위에서만 한다. 5개국 대시보드 각각 호출해 수집량을 표시하는 A 시제품은 가능하지만 전 세계 country를 전부 호출하는 설계는 피하고 B 집계 API를 사용한다(F10).
- 시간 슬라이더는 B 시간 버킷 API 이후에만 활성화한다. firstSeenAt 하나로 확산 애니메이션을 만들지 않는다(F15).
- 회전 정지 버튼, 모션 축소 설정, 캔버스 밖 국가 선택 목록, WebGL 실패 시 동일 데이터 목록을 제공한다(F05). CSS reduced-motion만으로 JS 애니메이션이 중지되지는 않는다.

## 9. 새로운 Information Architecture

```text
세계 탐색 / (기본 workspace)
 ├─ 국가 선택·분야/테마 필터 (동일 화면 상태)
 ├─ 국가 패널 [요약 | 테마 | 보도 언급]
 ├─ 이슈 패널 [국가 비교 | 대표 기사]
 └─ 기사 읽기 패널 /articles/:articleId (B)
탐색 /explore (같은 필터·결과 컴포넌트, 목록에 집중)
내 뉴스 /me (회원: 관심 콘텐츠 | 저장 기사 | 관심사)
로그인 /login · 회원가입 /signup (독립 진입 가능, 맥락 복귀)
```

F03의 URL 예시는 `/?issue=123&compare=KR,US`, `/?country=KR`, `/explore?field=1&theme=7&country=KR`다. 이는 **제안 URL**이며 현 route가 아니다. country는 발행국 탐색, compare는 이슈 비교의 선택 국가로 구별한다. 이름 대신 ID를 사용한다. F02의 `/articles/:articleId`는 새로고침에서도 ID로 조회되는 독립 주소다.

분야 화면은 필터로, 테마 전체는 같은 화면 확장 목록으로, attention은 국가 패널 탭으로, articles 더보기는 inline 확장으로 합친다. Explore는 별도 계층의 부모가 아니라 동일 탐색 상태를 넓은 목록 레이아웃으로 보여주는 대등한 목적지다. 뒤로가기는 사용자가 실제 방문한 상태를 복원하며 분야→테마의 DB 관계를 강제로 재방문시키지 않는다.

## 10. 화면별 redesign proposal

아래 component명은 제안이며 새 파일을 작성한 것이 아니다. 우선순위/지원도는 괄호의 기능 ID가 15장 표와 연결된다.

### 10.1 메인: 세계 탐색 workspace (F03~F07, F08/F10은 확장)

| 항목 | 제안 |
|---|---|
| 목적 | ‘지금 무엇을 비교할지’ 정하고 1~2회 선택으로 뉴스에 도달 |
| 핵심 정보 | TOP5 이슈 제목·테마·24h 보도량, 최초 관련 기사 시각, 선택국/이슈 범위, 논조 n |
| interaction | 홈 노출 분야→테마 필터, 이슈 선택, 국가 선택, 전체/선택국 비교, 기사 선택 |
| API | global/issues, by-field, country, global issue detail, issue overview; 국가 주요 이슈/전수 지도는 B |
| DB | issue/theme/field, article 집계, country/mention |
| 현재 대비 | 수집 KPI를 작은 상태줄로 축소, 이슈/지도/기사 관계를 우선. 더보기 화면 누적 제거 |
| component | ExploreWorkspace, ScopeBar, IssueRankList, GlobeStage, ContextPanel, CountryComparison, ArticleRows |
| depth | workspace D0, 국가/이슈 패널 D1, 기사 D2 |

데스크톱은 지도와 문서형 패널을 함께 두되 기사 비교 때 읽기 영역을 넓힌다. 모든 화면에 56:44 비율을 고정하지 않는다. 화면 상단에는 ‘선택 이슈 / 발행국 범위 / 기간’이 한 줄로 남는다. 홈의 분야 선택기는 다른 페이지를 먼저 방문하지 않아도 찾을 수 있어야 한다.

초기에는 TOP5와 전역 catalog만 요청한다. 이슈/국가 상세는 선택 후 조회하고, compare 국가별 응답은 `(issueId,countryCode,limit)` 키로 캐시한다. 이슈 이름이나 국가 개수 등을 보여주려고 TOP5 전체 상세를 무조건 선요청하지 않는다. 서버 응답 이후 선택된 항목이 바뀌었다면 늦은 응답을 폐기한다.

### 10.2 국가 패널 (F07/F08)

| 항목 | 제안 |
|---|---|
| 목적/핵심 정보 | 선택국에서 수집한 기사·테마·다른 나라 언급을 파악 |
| interaction | 요약/테마/언급 탭, 방향 전환, 테마 선택, 명시적 이슈 비교 진입 |
| API/DB | countries/{code}, popular; article/mention/theme. 국가 이슈와 전수 분야 분포는 새 B 집계 |
| 변경점 | attention 독립 화면 제거, TOP10을 ‘상위 테마’로 정확히 표기 |
| component/depth | CountryPanel, MentionDirectionTabs, ThemeTrendRows / D1 |

### 10.3 탐색/테마 화면 (F03/F07/F09)

| 항목 | 제안 |
|---|---|
| 목적/핵심 정보 | 분야→테마→기사를 이동 없이 좁히고 이슈 없는 기사도 발견 |
| interaction | 분야 필터·테마 검색·발행국 조합, 테마 선택 즉시 대표 기사, 이슈 칩 선택 |
| API/DB | by-field + theme overview / field-theme-article, nullable issue |
| 변경점 | themes/field/theme 중복 목록 합침. ‘대표 기사 최대10’ 범위 표시. 전수 검색/기간/정렬은 B 이후 |
| component/depth | TaxonomyFilter, ThemeSummary, IssueChips, ArticleRows / D1 |

### 10.4 이슈 비교 화면 (F04/F06)

| 항목 | 제안 |
|---|---|
| 목적/핵심 정보 | 같은 이슈의 국가별 보도 방향과 기사 출처 비교 |
| interaction | 지도/행에서 국가 선택, 두 국가 비교, 표본 기준 설명, 기사 열기 |
| API/DB | global issue detail + issue overview(countryCode), article/issue/country |
| 변경점 | 이슈를 유지하며 국가를 바꿈. 전체기간 KPI와 24h 논조를 시각적으로 분리. 대표 기사는 현재 전체기간임을 표시 |
| component/depth | IssueContext, ToneComparisonRows, ComparisonArticles, SampleNotice / D1 |

모든 통계를 24h로 통일하고 싶다면 B 기간 계약을 추가해야 한다. 전체기간 대표 기사를 24h 논조의 근거 표본처럼 제시하지 않는다. 평균과 표준편차만으로 긍정/중립/부정 기사 비율을 계산할 수 없으므로 그 비율 그래프는 B 집계 이후 제공한다.

### 10.5 기사 읽기 (F02/F14)

| 항목 | 제안 |
|---|---|
| 목적/핵심 정보 | 기사를 식별하고 근거 출처로 이동 |
| interaction | 기사 제목 선택, 원문 열기, 저장, 같은 이슈로 복귀 |
| API/DB | 신규 article detail / id,url,original_title,translated_title,publisher,publisher_country_code,published_at,theme/issue; summary는 nullable |
| 변경점 | 제목·출처·국가·시각·선택적 요약을 표시. 본문 전문이 있는 것으로 가정하지 않음 |
| component/depth | ArticleReader, SourceLink, ClassificationPath, BookmarkAction / D2 |

원문 링크/원제 fallback은 B로 먼저 제공한다. 번역/요약 생산을 기다리느라 읽기 기능 전체를 막지 않는다. null 요약은 비워두고 제목으로 요약을 만들어내지 않는다.

### 10.6 로그인/가입과 내 뉴스 (F11~F13)

| 항목 | 제안 |
|---|---|
| 목적/핵심 정보 | 계정 진입과 재방문할 관심 이슈/기사 보관 |
| interaction | 이메일 인증·로그인, 관심사 건너뛰기/저장, 내 뉴스 탭·저장 취소 |
| API/DB | 기존 auth6 + 신규 me/보호 조회, users + 신규 관심/북마크 관계 |
| 변경점 | 헤더의 인증 상태 분기, 세션 복원, 저장 의도 복원. 비회원 뉴스 열람 유지 |
| component/depth | AuthScreen, SessionBoundary, InterestSetup, MyNews, SavedArticles / 인증 D1, 내 뉴스 D1 |

### 10.7 시각 언어·모바일·상태 설계 (F05/F06)

데이터 형태마다 표현을 달리한다. 이슈는 큰 제목과 출처 범위를 갖는 편집형 행, 국가 비교는 정렬된 표/범위 막대, 테마 추이는 공통 시간축의 작은 그래프, 기사는 구분선 중심 목록으로 만든다. 모든 항목을 둥근 카드로 감싸지 않는다.

타이포그래피는 기존 Pretendard 계열을 유지하고 본문 14~16px, 보조 12~13px, 주요 제목 24~32px를 목표로 한다. 숫자는 tabular-nums로 비교한다. 제목·테마·기사량·출처 순의 시각 위계를 둔다. 수집 총량은 이슈 제목보다 강하게 보이지 않게 한다.

색은 액션/선택 강조와 논조 척도를 분리한다. 빨강/초록만으로 의미를 전달하지 않고 부정/중립/긍정 라벨·숫자·범례를 병기한다. 논조를 ‘해당 국가의 공식 입장’이나 ‘우호 국가’로 표현하지 않는다. 지도는 어두운 배경을 유지할 수 있지만 읽기 패널은 밝게 유지해 대비를 역할에 사용한다.

모바일에서는 읽기 영역을 기본으로 하고 작은 지도와 확장 버튼, 하나의 bottom sheet를 제공한다. sheet 위에 sheet를 쌓지 않는다. 두 국가 비교는 국가 토글과 동일 위치의 기사 행으로 바꾸고 가로 스크롤 카드 2열을 강제하지 않는다. 검색/국가 목록만으로 지도와 같은 기능을 사용할 수 있어야 한다.

전환은 선택 관계와 시점 이동을 설명하는 용도로만 사용한다. 상태 갱신 때 전체 지구본을 재생성하지 않는다. 새 패널은 제목으로 focus 이동, 닫기 시 원래 버튼으로 복원, Escape·Tab 순환을 제공한다. loading은 지도와 패널을 분리하고 재조회 실패는 이전 데이터+실패 배너+재시도로 처리한다. empty는 ‘수집 없음/기간 내 없음/이슈 미할당/조건 불일치/분석 미제공’을 데이터로 구별할 수 있는 범위에서만 구별한다.

## 11. 주요 사용자 Journey

**세계 이슈 비교(F04):** 홈 이슈를 선택(1) → 국가를 선택(2) → 해당국 대표 제목/매체가 바로 보인다. 비교국 추가(3) 시 두 열이 된다. 같은 이슈를 유지하므로 이전 화면을 다시 방문하지 않는다. API의 각 국가 대표 기사 요청은 독립 오류 처리한다.

**국가에서 탐색(F07/F08):** 국가 선택(1) → 테마 선택(2)으로 기사를 읽는다. 국가 주요 이슈 B가 완료되면 국가→이슈도 2회로 가능하다. 다른 국가의 보도를 비교할 때 발행국 filter를 몰래 버리지 않고 비교 모드로 전환됐음을 범위줄에 명시한다.

**분야에서 탐색(F03/F09):** 홈에 있는 분야(1) → 테마(2) 선택 후 기사 결과를 바로 제공한다. 최신순·기간·논조를 서버에서 전수 적용하는 기능은 B 이후 활성화한다. 이슈가 없는 기사도 테마 결과에 남겨 수집과 군집 사이의 지연을 숨기지 않는다.

**회원 재방문(F11/F12):** 세션 확인 → 내 뉴스(1) → 관심 이슈(2)에서 세계 보도를 비교한다. 저장 기사도 내 뉴스 탭에서 바로 연다. 로그인 페이지를 탐색의 부모로 만들지 않는다.

**저장 중 로그인(F11/F12):** 기사에서 저장 → 로그인 화면으로 대체 → 인증 완료 → 기사 맥락 복원 → 저장 요청 결과 표시. 자동 재시도 정책을 적용하되 중복 저장은 서버 unique와 멱등 쓰기로 막는다. 비밀번호 등 입력값은 URL/복귀 상태에 보관하지 않는다.

## 12. Backend/API 추가 필요 사항

아래 경로는 **제안 계약**이며 현재 구현으로 표시하지 않는다.

| ID | 추가/보완 | 필수 계약·경계 |
|---|---|---|
| F01 | 시간 규약 보정 | UTC 경계 일치, offset 포함 timestamp, periodStart/periodEnd/timeBasis, 조회시각과 데이터 기준시각 구분 |
| F02 | 대표 기사 DTO 확대, GET /articles/{id} | URL, 원제 fallback, 발행국·themeId/issueId, nullable summary, 안전한 공개 필드만. deleted/missing 상태 구별 |
| F08 | GET /countries/{code}/issues, /countries/{code}/distribution | 발행국·published_at·deleted_at 기준, 기사 수/기간/분모, 상위 N와 기타/미분류 구별 |
| F09 | GET /articles, GET /issues | country/field/theme/issue/기간/논조/정렬·cursor. 동점은 id로 안정 정렬, limit 후 프론트 필터 금지 |
| F09 | issue/theme overview 개선 | 실제 themeId/fieldId 및 기간/정렬/totalCount 반환. 국가 적용이 기사만인지 이슈 목록도인지 명시 |
| F10 | GET /countries 및 지도 집계 | 국가 마스터+수집 지원 여부+좌표, 대량 dashboard N회 호출 대신 필요한 집계만 |
| F06 | 논조/언급 설명 메타 | scoreScale, 표본 수, 집계기간, 원건수/분모, 긍정중립부정 비율은 별도 count 집계 |
| F11 | GET /users/me, 인증·인가 연결 | 세션 userId 검증, 비회원401/권한403 정책, logout 후 캐시 제거, CSRF/Cookie 검증 |
| F11 | 비밀번호 재설정·탈퇴 | 기존 users로 가능하나 이메일 인증 목적 분리, 세션 무효화, 오류 계약 필요. SSAFY는 채택 시 별도 |
| F15 | GET /issues/{id}/timeline | 시간 버킷별 국가 기사 수, MIN(published_at), n. 남아 있는 기사 기반 재계산이라는 한계 표시 |

같은 이슈의 국가별 대표 기사 비교 자체에는 새 API가 필수는 아니다. 현재 overview를 국가별로 호출할 수 있다(A). 다만 한 요청으로 비교 세트를 받거나 동일 기간의 전체 기사 비교를 원하면 B 확장이 필요하다. DB에 없는 ‘관점 요약’ 텍스트까지 현재 API로 가능하다고 설명하지 않는다.

## 13. DB 변경이 필요한 제안

| ID | 최소 저장 설계(제안) | 추가 결정/작업 |
|---|---|---|
| F12 | user_country_interest(user_id,country_code), user_theme_interest(user_id,theme_id), 필요 시 user_field_interest | 각 쌍 unique, FK, 생성 시각. 분야와 테마 중복 선택 의미 정의 |
| F12 | user_issue_follow(user_id,issue_id,created_at), user_article_bookmark(user_id,article_id,created_at) | follow=관심/저장 이슈 통합. 동명이슈 병합·기사 삭제·계정 탈퇴 처리 |
| F12 | 저장 필터가 필요할 때 user_saved_filter | 단순 관심 관계와 구분. JSON 조건 사용 시 버전·유효 ID 검증 |
| F13 | user_article_history(user_id,article_id,last_viewed_at), notification/subscription 상태 | 보관 기간, 삭제/옵트아웃, 중복 발송 방지, 재처리 기준 |
| F14 | issue.summary 및 생성 상태/버전; 기사 번역/요약 pipeline | article 컬럼은 이미 있지만 생성/저장 경로 추가 필요. 부분 실패·재처리 규칙 |
| F16 | 논조 분석 상태/모델 버전, 선택적 source 식별/수집 현황 | dummy50과 중립 분리. 표본 품질을 설명할 영속 근거 |
| F16 | country_tone snapshot 생산/보관 정책 | 기존 테이블만으로 기간/모델 버전 구분이 충분한지 검토. append 주기·보관·재계산 정의 |
| F17 | 기사 embedding 재보관 또는 별도 검색 인덱스 | 전체 임베딩 재생성 비용·저장소·백필·검색 품질을 확인한 뒤 결정 |

시간 정합성(F01)은 B 수정으로 끝날 수도 있으나 기존 데이터의 UTC/KST 혼재가 확인되면 **C 데이터 보정**으로 분리한다. FK/필터 인덱스는 성능 측정 후 후보를 정한다. DOCS/PERF에 실제 측정치가 없으므로 특정 인덱스로 몇 배 개선된다고 약속하지 않는다. `ddl-auto:update`와 Flyway를 함께 쓰므로 실 DB 구조가 migration만의 결과와 다를 가능성도 검증한다.

## 14. 프론트 기술 구조 개선안

| ID | 현재 | 권고와 근거 |
|---|---|---|
| F03 | App에 화면 조건·조회·history 집중 | workspace 상태, 화면 컴포넌트, API adapter 분리. country/field/theme/issue/compare URL 직렬화와 browser history 연결 |
| F03 | router 없음 | React Router 등 단일 라우팅 도구 도입 검토. 기능 이유는 깊은 링크/Back/인증 복귀이며 프레임워크 교체는 불필요 |
| F03 | useState/props | 계속 사용. 공유 탐색 상태는 reducer/context 정도로 정리; Redux 전면 도입 근거 없음 |
| F06 | useResource | 취소/재시도 유지, key별 캐시·stale 표시·독립 실패·중복 요청 제거. 서버 상태 라이브러리는 복잡도 증가 시 한 가지로 판단 |
| F11 | GET 전용 fetch helper | method/body/credentials 및 401·CSRF 처리를 확장. 동일 출처 쿠키는 fetch 기본 동작 가능, cross-origin은 include+CORS 점검 |
| F05 | CSS Modules/tokens | 유지. 중복 override 정리, 반응형 레이아웃·타이포·상태 토큰 정의 |
| F04/F05 | 직접 Three 구현 | 유지. 지도 선택 계약을 React 상태와 연결하고 오류/성능/모션 제어 보완. 엔진 교체부터 시작하지 않음 |
| F07/F15 | HTML/CSS 막대, 별도 chart 없음 | 단순 비교/추이는 기존 방식 또는 SVG로 충분. 시간축 복잡도 증가 때만 chart 도입 검토 |
| F05 | 컴포넌트 라이브러리 없음 | 기존 UI 재사용. 복잡한 dialog의 접근성 구현 부담이 크면 작은 primitive 도입만 검토 |
| F06 | 미사용 목업 파일·오래된 문서 혼재 | 실제 import 그래프 기준으로 추후 정리/격리. 이번에는 제거하지 않음 |

지도 GeoJSON은 GitHub raw URL에 런타임 의존하고 실패 시 근사 형상을 만드는 경로가 있다. 실제 경계처럼 오해하지 않게 fallback 상태를 표시하고, 검증된 지도 자산을 로컬 정적 파일로 제공하는 방안을 검토한다(F05). 현재 Nginx의 `try_files ... /index.html`은 SPA 깊은 주소 제공의 기반이지만 클라이언트 URL 파싱은 새로 필요하다.

## 15. 구현 우선순위

**모든 제안은 다음 기능 ID의 범위에 포함된다.** High/Medium/Low는 상대 평가다. Backend/DB Yes는 필요한 형태의 코드/데이터 구조가 있다는 뜻이며 운영 가용성 보증이 아니다. 순수 UI는 데이터 요구가 없으므로 기존 API/DB로 충족하는 Yes로 표시했다.

| ID | 기능 묶음 | P | A/B/C | 사용자 가치 | 개발 난이도 | Backend 지원 | DB 지원 |
|---|---|---|---|---|---|---|---|
| F01 | 시간 규약·기간 계약 정합성 | P0 | B, 혼재 보정 C | High | High | Partial | Partial |
| F02 | 원제/원문 연결·기사 상세 | P0 | B | High | Medium | Partial | Yes |
| F03 | 얕은 IA·URL·탐색 필터·화면 분리 | P0 | A | High | Medium | Yes | Yes |
| F04 | 이슈 유지 국가 비교·지구본/표본 통일 | P0 | A | High | Medium | Yes | Yes |
| F05 | 읽기 위계·반응형·접근성·지도 fallback | P0 | A | High | Medium | Yes | Yes |
| F06 | 상태/용어·갱신·캐시·기간/분모 메타 정리 | P0 | A+B | High | Medium | Partial | Yes |
| F07 | 최초 관련 보도·세계 분야 비중·테마 추이·언급 통합 | P1 | A | High | Low | Yes | Yes |
| F08 | 국가 주요 이슈·국가 분야 전수 분포 | P1 | B | High | Medium | Partial | Yes |
| F09 | 전체 기사/이슈 탐색·기간/논조/조합 필터·동일 이슈 관련 기사 | P1 | B | High | High | Partial | Yes |
| F10 | 국가 catalog/지도 집계·전수 언급 지도 | P1 | B | Medium | Medium | Partial | Yes |
| F11 | 가입/로그인 UI·세션 복원/인가·계정 관리 | P0 | B(기존 auth 연동 일부 A) | High | High | Partial | Yes |
| F12 | 관심 국가/분야/테마/이슈·북마크·개인화 홈/필터 | P1 | C | High | High | No | No |
| F13 | 최근 열람 동기화·알림 | P2 | C | Medium | High | No | No |
| F14 | 기사 번역/요약·이슈 설명 생산/노출 | P2 | C | High | High | No | Partial |
| F15 | 보도 시간 추이·국가별 최초 관련 기사 | P2 | B | Medium | Medium | No | Yes |
| F16 | 분석 상태/품질·출처 근거·역사 snapshot | P2 | C | High | High | No | Partial |
| F17 | embedding 기반 의미 추천/검색 | P2 | B(이슈 후보)+C(기사) | Medium | High | No | Partial |

F14의 완성된 요약은 P2지만 F02의 읽기 가능한 제목/원문은 P0다. F16 모델 상태 저장은 확장으로 두되, 현재 fallback 혼입이 실제 확인되면 해당 데이터로 논조 비교를 공개하기 전에 그 부분을 P0로 승격한다. 회원 기능 출시는 F11 검증과 F12 저장 기반 완료 후로 나눈다.

## 16. 단계별 개발 계획

일정 수치는 팀 규모/운영 상태를 모르는 상황에서 정하지 않는다. 아래는 의존성과 완료 기준이다. **이번 작업에서 실행하는 단계가 아니라 다음 구현 계획**이다.

| 단계 | 범위 | 완료 판단 |
|---|---|---|
| 0. 계약/데이터 확인 | F01/F02/F06, 운영 read-only 표본 점검 | URL·원제·번역제·요약 null 비율, UTC/KST 규약, 실제 응답 DTO, 미분류/논조 fallback 여부 기록 |
| 1. 공개 탐색 P0 | F03/F04/F05 + 원문 연결 | 홈 이슈→국가 기사 2회, 분야→테마 기사 2회, D3 이하, URL 새로고침/Back/모바일 동작 |
| 2. 기존 데이터 확장 | F07/F08/F09/F10 | 분포 분모/기간 명시, 서버 필터와 total/cursor 일치, 0건·미분류 처리 |
| 3. 인증 도입 | F11 (1~2와 독립 개발 가능) | 이메일 인증/가입/로그인/로그아웃/세션 복원·만료, 권한 경계 확인, 공개 열람 유지 |
| 4. 재방문 기능 | F12, 3과 기사 ID 계약 이후 | 관심/저장 멱등 처리, 다른 세션에서 유지, 로그인 복귀/삭제 기사/탈퇴 처리 |
| 5. 확장 | 선택한 F13~F17 | 데이터 생산·저장·품질·비용 검증 후 실제 값으로만 출시 |

다음 구현 때 필요한 검증은 API DTO 계약 테스트, UTC 경계/삭제·미할당 기사 집계 테스트, 국가 비교와 필터 유지·Back/새로고침 여정, 360/768/1280px 레이아웃, 키보드/스크린리더 focus, WebGL/네트워크 실패 상태다. 기존 frontend 테스트는 fetch mock·SSR 중심이며 실제 운영 DTO 원문 링크, browser navigation, 모바일·인증의 종단 검증은 하지 않는다. 기존 테스트가 있다는 이유로 이 범위가 검증됐다고 판단하지 않는다.

측정 지표는 작업 성공률·이슈에서 국가 기사까지 선택 수·원문 도달률·이슈 비교 완료율·모바일 가로 overflow·초기 및 선택 후 데이터 대기시간을 기록한다. 운영 응답 성능/사용자 행동의 현재 수치는 없다. 먼저 baseline을 얻고 예산을 합의한다.

## 17. 위험 요소 / 의사결정이 필요한 항목

### 17.1 구현 전에 결정할 사항

| 결정 | 권고안 | 영향을 받는 범위 |
|---|---|---|
| 첫 개편의 핵심 작업 | 세계 이슈 선택→국가별 보도 비교 | IA·메인 배치·검증 시나리오 |
| 국가 탐색 범위 | 우선 기존 5개 발행국; 다른 언급국은 별도 범위로 표시 | V8 마스터가 있다고 전 세계 수집 서비스로 확대하지 않음 |
| 시간/기간 정의 | 저장/응답 UTC 정합성을 확보하고 화면에 KST 표기, 발행/수집 기준 분리 | F01, 모든 순위·추이·갱신 설명 |
| 기사 읽기 수준 | 원제 fallback+원문부터, 요약/번역 보장은 후속 | B와 C 작업량·읽기 경험 |
| 모바일 우선 범위 | 첫 P0에 핵심 탐색·비교·원문 포함 | 고정폭 제거 및 지도 축소 UX |
| 회원 1차 기능 | 이메일 계정+관심 국가/테마/이슈+북마크 | SSAFY·최근 본 기사·알림은 후순위 |
| 개인화 기준 | 관심 이슈 중심, 다른 국가 보도 비교 유지 | 관심 국가만의 폐쇄적 피드 방지 |
| 표본/분석 실패 표현 | 30건 기준의 근거 재검토, 지도·패널·tooltip 일치; fallback은 중립으로 설명하지 않음 | F04/F16 우선순위 |
| 계정 복구/탈퇴 및 데이터 보관 | 공개 회원 출시 전 지원 범위·삭제 기준 확정 | 세션/개인 저장/이력 API |

### 17.2 코드에서 확인한 위험과 미확인 영역

- **원문 도달 불가:** 프론트 safeUrl 처리가 있어도 URL 미제공 계약을 해결하지는 못한다. DTO/projection 수정이 선행된다.
- **번역/요약 빈값:** nullable 컬럼과 시드 데이터는 실제 파이프라인의 생산 보장이 아니다. 현재 writer 기준으로 점검해야 한다.
- **시간 혼재:** UTC writer/KST SQL/프론트 해석의 불일치. 실제 행 점검 없이 순위·신규 배지를 신뢰할 수 없다.
- **논조의 의미:** 텍스트 긍정/부정 모델 점수를 국가의 의도·정치적 입장·매체 신뢰도로 확대 해석하지 않는다. 평균/SD는 실제 의견 분포나 긍정 비율의 대체가 아니다.
- **분야별 논조 적용:** sentiment adapter는 field_id/theme_id를 받을 수 있지만 현재 `process_article`은 `analyze_sentiment(article)`로 호출한다. 이미 분류된 분야를 전달하지 않으므로 분야별 채점이 실제 적용된다고 소개하지 않는다. fallback 상태 보존과 함께 검증한다(F16).
- **모집단 편중:** country 마스터 전체와 발행 기사 수집국은 다르다. 수집량 순위를 세계 관심도/중요도로 표현하지 않는다.
- **과거 재구성 한계:** first_seen_at은 사건 발생이 아니며 삭제·재분류된 기사 때문에 과거 시점 상태를 완전히 복원할 수 없다. snapshot이 필요하면 C다.
- **고유 이슈 이름:** V7 unique(name), V6_1 병합과 writer upsert로 이름이 같은 이슈의 ID/맥락이 합쳐질 수 있다. 회원 팔로우·장기 추적은 병합 정책을 먼저 정의한다.
- **운영 DB drift:** Flyway와 ddl-auto:update, 실제 마이그레이션 이력·수동 변경은 확인 필요다.
- **성능 미실측:** 지도 전수 요청·국가 비교·기사 검색 확장 전에 query plan/응답량을 측정한다. 이번에는 서비스 부하를 주지 않았다.
- **문서 drift:** frontend README/DECISIONS와 DOCS API의 일부 내용은 현재 코드보다 오래됐다. 모든 신규 구현의 기준은 재합의한 실제 계약으로 통일해야 한다.

이 문서의 범위는 repository 기반 실현 가능성 감사와 개편 설계다. 운영 값, 실제 화면 스크린샷, 사용자 테스트를 측정한 결과로 해석하면 안 된다. 소스 코드 구현·route 변경·패키지 설치·DB 변경·API 구현·git add/commit/push는 수행하지 않았다.
