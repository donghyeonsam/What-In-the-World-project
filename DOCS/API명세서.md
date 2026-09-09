# API 명세서

> 기준: 현재 구현된 조회 API 7개 및 기존 회원 기능 기획 목록
>
> 갱신일: 2026-09-08
>
> 조회 API는 모두 로그인 없이 호출할 수 있으며 `/api/v1` 경로를 사용한다.

요청·응답 상세와 집계 기준은 [조회 API 문서](../backend/docs/read-api.md)를 참조한다.
실행 중인 서버의 `/swagger-ui.html`에서 요청을 실행할 수 있다.
URL의 쿼리 파라미터 값은 기본값이며, 조회 개수는 모두 1~10 범위에서 변경할 수 있다.

## 글로벌 대시보드

| 기능 | 화면 | Method | URL | 진행 상황 |
|---|---|---|---|---|
| 전체·최근 24시간 수집 기사 수 및 글로벌 이슈 TOP 5 조회 | DSBD-001 | GET | `/api/v1/global/issues` | 구현 완료 |
| 글로벌 이슈 상세 정보 및 국가별 논조 조회 | DSBD-003 | GET | `/api/v1/global/issues/{issueId}` | 구현 완료 |
| 이슈 미리보기·국가별 논조·대표 기사 조회 | DSBD-003 | GET | `/api/v1/issues/{issueId}/overview?articleLimit=3` | 구현 완료 |

글로벌 이슈 TOP 5는 고정 순위 조회이며 별도 `sort`·`limit` 파라미터를 제공하지 않는다.
기존에 분리되어 있던 전체·금일 기사 수, 국가별 논조, 대표 기사 조회는 위 API 응답으로 통합되었다.
국가별 논조는 `toneAvg`, `toneMax`, `toneMin`, 모집단 표준편차 `toneSd`, 집계 대상 기사 수
`articleCount`를 반환한다. 논조 집계는 최근 24시간 발행 기사 기준이다.

## 국가별 대시보드

| 기능 | 화면 | Method | URL | 진행 상황 |
|---|---|---|---|---|
| 국가 대시보드 조회 (최근 24시간 수집 기사 수·순위·인기 테마·국가 간 언급 비율·대표 기사) | DSBD-002 | GET | `/api/v1/countries/{countryCode}` | 구현 완료 |
| 국가별 인기 테마 및 시간별 기사 수 추이 조회 | DSBD-002, DSBD-004 | GET | `/api/v1/countries/{countryCode}/themes/popular?limit=3` | 구현 완료 |
| 테마 개요·주요 이슈·대표 기사 조회 | DSBD-005 | GET | `/api/v1/themes/{themeId}/overview?issueLimit=3&articleLimit=10` | 구현 완료 |
| 분야별 테마 ID·이름·최근 24시간 기사 수 조회 | 미지정 | GET | `/api/v1/themes/by-field` | 구현 완료 |

인기 테마 10개가 필요한 화면에서는 동일 API에 `limit=10`을 전달한다.
국가 대시보드의 `todayArticleCount`는 자정부터가 아닌 최근 24시간 수집 기사 수다.
분야별 테마 조회의 화면 ID는 기존 명세에 없어 미지정으로 표시했다.
기존 테마 검색 API는 미구현이며, 현재 구현된 조회 API 목록에는 포함하지 않는다.

## 네비게이션 바

아래 회원 기능은 기존 기획 목록이며 아직 구현되지 않았다.

| 기능 | 화면 | Method | URL | 진행 상황 |
|---|---|---|---|---|
| 로그인 | USR-001 | POST | `/api/v1/auth/login` | 진행 전 |
| 회원 가입 | USR-001 | POST | `/api/v1/auth/signup` | 진행 전 |
| 로그아웃 | USR-001 | POST | `/api/v1/auth/logout` | 진행 전 |
| 회원 탈퇴 | USR-001 | PATCH | `/api/v1/users/withdraw` | 진행 전 |
| 싸피 로그인 / 회원가입 | USR-001 | POST | `/api/v1/auth/ssafy` | 진행 전 |
| 이메일 인증번호 전송 | USR-001 | POST | `/api/v1/auth/email/send` | 진행 전 |
| 이메일 인증번호 검증 | USR-001 | POST | `/api/v1/auth/email/verify` | 진행 전 |
| 이메일 중복확인 | USR-001 | GET | `/api/v1/auth/exists?email={email}` | 진행 전 |
| 비밀번호 재설정 인증코드 발송 | USR-001 | POST | `/api/v1/auth/password/email/send` | 진행 전 |
| 비밀번호 재설정 인증코드 검증 | USR-001 | POST | `/api/v1/auth/password/email/verify` | 진행 전 |
| 비밀번호 재설정 | USR-001 | PATCH | `/api/v1/auth/password` | 진행 전 |

## 집계

| 구분 | API 수 |
|---|---:|
| 글로벌 대시보드 (구현 완료) | 3 |
| 국가별 대시보드 (구현 완료) | 4 |
| 네비게이션 바 | 11 |
| **전체** | **18** |

구현 완료된 조회 API는 7개다. 동일 경로의 조회 개수 변경은 별도 API로 집계하지 않으며, 미구현 테마 검색은 위 집계에서 제외한다.
