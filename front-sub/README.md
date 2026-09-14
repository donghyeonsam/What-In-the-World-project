# WITW — Frontend Redesign Prototype

기존 repository를 수정하지 않고 `front-sub/`에 만든 독립 React 프로젝트입니다. 이 폴더의 기존 감사 요청/개편안 문서도 변경하지 않았습니다. 기존 `frontend/`와 `backend/`는 런타임 import하지 않습니다. 지구 텍스처만 기존 자산을 이 프로젝트의 `public/earth.jpg`로 복사했습니다.

## 실행

```powershell
cd front-sub
npm.cmd install
npm.cmd run dev
```

접속: **http://127.0.0.1:5175**. 기존 frontend 개발 포트 5174와 다릅니다.

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run preview
```

preview: http://127.0.0.1:4175. 실제 API 프록시는 개발 서버에서만 동작합니다. 배포 시 `/api`를 기존 backend로 전달하는 별도 호스팅 프록시를 설정하거나, CORS 허용된 `VITE_API_BASE_URL`을 빌드 환경에 지정하세요. 이 작업에서는 기존 Nginx/배포 설정을 변경하지 않았습니다.

## 데이터 모드

화면 상단 **데이터 설정**에서 전환합니다. 기본은 백엔드 없이 실행되는 **데모 모드**입니다. 선택은 이 브라우저에 보관됩니다. `.env.example`을 `.env.local`로 복사해 최초 기본값/서버 주소를 지정할 수 있습니다.

- **데모:** 모든 뉴스·기사·국가별 통계·증감률·시간 추이를 일관된 가상 데이터로 구성합니다. 실제 언론사의 기사처럼 가장하지 않으며 원문 링크를 만들지 않습니다.
- **기존 API:** 아래 실제 구현된 API만 호출합니다. 서버 오류를 데모 데이터로 자동 대체하지 않습니다. 실제 응답에 없는 기사 요약/URL은 ‘미제공’으로 표시하고 실제 기사에 가상 값을 섞지 않습니다.
- 신규 API가 없는 **관심 국가/테마·이슈 팔로우·북마크**는 두 모드 모두 브라우저 저장 데모입니다. 데모/실제 모드 및 로그인 이메일별로 저장 공간이 분리됩니다. 서버 동기화는 하지 않습니다.
- **시간별 이슈 추이·개인화 피드·전체 기사 검색**은 데모 모드에서 작동합니다. 실제 모드에서는 제한을 설명하거나 기존 테마 대표 기사 조회만 제공합니다.

## 구현한 탐색

- 어두운 지구본과 밝은 읽기 패널, 편집형 이슈 목록, 테마 카드, 국가별 비교 행으로 정보 위계를 구분했습니다.
- 회전 가능한 Three.js 지구본, 국가 라벨, 5개국 선택 버튼, 이슈별 평균 논조 pin 색상, 회전 정지, 모션 축소 설정을 지원합니다. 경계 polygon 채색이 아닌 국가 포인트 방식입니다.
- 홈 이슈 → 국가 선택 **2회**로 해당 이슈의 국가별 대표 기사를 표시합니다. 최대 두 국가를 나란히 비교합니다. 국가 변경 시 이슈가 유지됩니다.
- 국가 패널에서 주요 테마·시간별 추이·국가 간 언급 방향·대표 기사를 탭으로 전환합니다.
- 분야 → 테마 선택과 기사 목록을 같은 탐색 화면에 배치했습니다. 제목/매체·발행국·논조·기간(데모) 필터가 작동합니다.
- 기사 읽기, 저장, 이슈로 이동, 관심사 기반 피드, 팔로우 해제를 제공합니다.
- 탐색 상태는 URL query에 저장되어 새로고침·브라우저 뒤로가기·공유가 가능합니다. 예: `/?issue=101&compare=KR,US`, `/?page=explore&field=1&theme=11`.
- 기사 읽기는 `article` query로 표시합니다. 데모 기사는 새로고침으로 복원됩니다. 실제 기사는 상세 조회 API가 없으므로 새로고침 시 해당 기사가 현재 응답/저장 목록에 없으면 복원 불가 안내를 표시합니다.
- 모바일에서는 세로형 지도/읽기 화면, 한 열 국가 비교, 접히지 않는 접근 가능한 필터를 제공합니다. 중첩 모달 대신 단일 dialog를 교체합니다.
- 키보드 검색, dialog focus trap/Escape/복귀, 로딩·오류·빈 상태, WebGL 실패 시 국가 목록 탐색을 지원합니다.

## 회원 기능

**데모 모드**에서는 이메일과 임의의 8자 이상 데모 비밀번호로 로그인합니다. 실제 계정은 만들어지지 않고 비밀번호는 저장하지 않습니다. 데모 회원가입 인증번호는 화면에도 표시되는 **AB12345**이며 이메일을 발송하지 않습니다. 관심사/기사 데이터는 `witw-sub-*` localStorage 키에만 저장됩니다. 데모 계정 체험용이므로 실제 비밀번호를 입력할 필요가 없습니다.

**실제 모드**에서는 기존 이메일 인증/가입/로그인/로그아웃 API를 사용합니다. 가입 후 별도 로그인이 필요합니다. 인증 상태 확인 API(`/users/me`)가 없으므로 실제 로그인 사용자 UI는 현재 페이지 세션에만 유지하며 새로고침 후 다시 로그인해야 합니다. 기존 서버의 세션 인가/CSRF/Secure cookie 보완은 이 독립 프론트에서 수정하지 않았습니다. 운영 회원 기능 완성을 의미하지 않습니다.

## API 대응

공통 prefix `/api/v1`, 개발 프록시 기본 목적지 `http://localhost:8080`.

| 기존 API | 연결 위치 |
|---|---|
| GET /global/issues | 홈 KPI / 이슈 TOP5 |
| GET /themes/by-field | 분야·테마 catalog |
| GET /countries/{code} | 국가 현황 / 양방향 언급 / 기사 |
| GET /countries/{code}/themes/popular?limit=10 | 국가 테마 추이 |
| GET /global/issues/{id} | 이슈 전체 기간 정보 |
| GET /issues/{id}/overview?articleLimit=10&countryCode=… | 이슈 논조 / 국가별 기사 비교 |
| GET /themes/{id}/overview?issueLimit=10&articleLimit=10&countryCode=… | 테마 대표 기사 / 주요 이슈 |
| POST /auth/email/send, /email/verify, /signup, /login, /logout | 실제 모드 인증 화면 |

이메일 중복 전용 `/auth/exists`는 별도로 호출하지 않으며 기존 전송/가입 API의 중복 오류를 표시합니다. `data` 필드 없는 인증 성공 응답도 처리합니다. 미지원 API를 404로 호출한 뒤 덮는 방식 대신 서비스 계층에서 명시적으로 demo/live를 분기합니다.

## 폴더 구조

```text
front-sub/
  FRONTEND_REDESIGN_AUDIT_REQUEST.md  # 기존 파일, 변경 없음
  FRONTEND_REDESIGN_PLAN.md           # 기존 파일, 변경 없음
  src/
    App.jsx                          # workspace, 탐색, 내 뉴스
    hooks.js                         # URL 상태, 취소 가능한 조회, 로컬 저장
    data/demo.js                     # 가상 관계 데이터
    data/api.js                      # 실제 API adapter / 데모 분기
    components/Globe.jsx             # 독립 Three.js 지구본
    components/Auth.jsx              # 데모/실제 인증
    components/UI.jsx               # 목록, 모달, 상태, 추이
    components/Icon.jsx
    styles.css
  public/earth.jpg                   # 복사된 독립 자산
  tests/                            # 데이터 계약 / DOM 여정 검증
  package.json / package-lock.json / vite.config.js
```

## 범위와 후속 작업

이 프로젝트는 개편 핵심 흐름을 실행 가능한 형태로 만든 독립 프로토타입입니다. 감사 문서의 P0~P2를 모두 운영 기능으로 완성한 것은 아닙니다. 다음은 기존 코드 변경 없이 구현할 수 없거나 이번 프로토타입에서 보류한 사항입니다.

- 실제 DB 시간대 불일치 수정, 번역/요약 생성, 원문 DTO 확장, 서버 검색/페이지네이션.
- 서버의 관심사/북마크/개인화 및 현재 사용자 조회·인증 보안 보완.
- 국가 전수 분포 지도, 국가 주요 이슈 전수 API, 실제 시간 슬라이더/확산 이력, 알림/최근 읽은 기사 동기화, embedding 검색.
- 실제 API 운영 서버에 대한 종단 테스트. 이 프로젝트 생성 중 실제 회원가입/이메일 발송 요청은 보내지 않았습니다.

Three.js 전용 번들은 약 500 kB(minified)로 빌드 경고가 발생할 수 있습니다. CSS 글꼴은 Google Fonts를 사용하지만 로드 실패 시 시스템 한글 글꼴로 대체됩니다. 지구본 텍스처는 로컬 파일입니다.

검증에는 빌드, 데이터/계약 테스트와 DOM 상호작용 테스트를 사용합니다. 이 작업 환경에는 연결 가능한 브라우저가 없어 실제 화면 스크린샷 및 기기별 WebGL·모바일 시각 검증은 수행하지 못했습니다.
