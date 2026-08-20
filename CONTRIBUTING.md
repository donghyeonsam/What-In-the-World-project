# 커밋 규칙

[Udacity Git Style Guide](https://udacity.github.io/git-styleguide/) + Jira 연동.

## 형식

```
<type>: <Subject>

<body>

<footer>
```

| 항목 | 규칙 |
|---|---|
| type | `feat` `fix` `docs` `style` `refactor` `test` `chore` |
| Subject | 50자 이내 · 대문자 시작 · 마침표 없음 · 명령형(`add`, not `added`) |
| body | 선택 · 72자 줄바꿈 · 무엇과 왜 (어떻게 제외) |
| footer | Jira 이슈 키 |

`feat` 새 기능 · `fix` 버그 수정 · `docs` 문서 · `style` 포맷팅 ·
`refactor` 리팩터링 · `test` 테스트 · `chore` 빌드·설정

Subject 영어, body 한국어 허용.

## Jira 연동

트리거는 **MR 설명**. 커밋 메시지 아님.

| MR 설명 | 효과 |
|---|---|
| `Resolves: S15P21D203-29` | 머지 시 이슈 완료 처리 |
| `See also: S15P21D203-29` | 코멘트·링크만 |

MR 생성 시 템플릿이 `Resolves: S15P21D203-` 까지 채움. 번호만 입력.

- 키 누락 시 Jira 미반영. 에러 없음
- master 직접 push 시 MR 부재로 미반영. 모든 작업 MR 경유
- 커밋 메시지의 키는 선택. 넣을 경우 footer에 둘 것 (키 10자, Subject 50자 초과 방지)

## 예시

```
feat: Add JWT-based login endpoint

세션 대신 토큰을 쓰는 이유는 분산 환경에서 세션 공유 비용 회피.
리프레시 토큰은 Redis에 저장해 강제 로그아웃 지원.

Resolves: S15P21D203-29
```

```
fix: Prevent duplicate consumer group offsets

See also: S15P21D203-31
```
