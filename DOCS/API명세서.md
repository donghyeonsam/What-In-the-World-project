# API 명세서

> 출처: Notion `API 명세서` 메인 페이지  
> 추출일: 2026-09-03  
> 범위: 메인 데이터베이스에 표시된 API 목록만 포함하며, 각 API 하위 페이지의 Request·Response 상세 명세는 포함하지 않음.

## 글로벌 대시보드

| 기능 | 화면 | Method | URL | 진행 상황 |
|---|---|---|---|---|
| 글로벌 이슈 TOP5 조회 | DSBD-001 | GET | `/api/v1/global/issues?sort=articleCount,desc&limit=5` | 진행 전 |
| 전체 수집 기사 개수 조회 | DSBD-001 | GET | `/api/v1/global/total-count` | 진행 전 |
| 금일 수집 기사 개수 조회 | DSBD-001 | GET | `/api/v1/global/today-count` | 진행 전 |
| 글로벌 이슈별 각 국 톤 조회 | DSBD-003 | GET | `/api/v1/global/issues/{issueId}/tones` | 진행 전 |
| 이슈 상세 정보 조회 | DSBD-003 | GET | `/api/v1/global/issues/{issue_id}` | 진행 전 |
| 글로벌 이슈별 대표 기사 3개 조회 | DSBD-003 | GET | `/api/v1/global/issues/{issue_id}/articles?sort=issue_similarity,desc&limit=3` | 진행 전 |

## 국가별 대시보드

| 기능 | 화면 | Method | URL | 진행 상황 |
|---|---|---|---|---|
| 금일 수집 기사 개수 조회 | DSBD-002 | GET | `/api/v1/countries/{country_code}/articles/today-count` | 진행 전 |
| 인기 테마 TOP3 조회 | DSBD-002 | GET | `/api/v1/countries/{country_code}/themes/popular?limit=3` | 진행 전 |
| 해당 국가 기준 국가별 관심도 조회 | DSBD-002 | GET | `/api/v1/countries/{country_code}` | 진행 전 |
| 인기 테마 10개 표시 | DSBD-004 | GET | `/api/v1/countries/{country_code}/themes/popular?limit=10` | 진행 전 |
| 해당 테마 대표기사 10개 조회 | DSBD-005 | GET | `/api/v1/themes/{theme_id}/articles` | 진행 전 |
| 테마 검색 | MDL-001 | GET | `/api/v1/themes/search?keyword={keyword}` | 진행 전 |

## 네비게이션 바

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
| 글로벌 대시보드 | 6 |
| 국가별 대시보드 | 6 |
| 네비게이션 바 | 11 |
| **전체** | **23** |
