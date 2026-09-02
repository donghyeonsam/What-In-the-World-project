# S15P21D203

SSAFY 15기 빅데이터 분산 트랙 · sub1 · D203팀

| | |
|---|---|
| GitLab | https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21D203 |
| Jira | https://ssafy.atlassian.net/jira/software/c/projects/S15P21D203/boards/15137 |

## 커밋과 MR

규칙: [CONTRIBUTING.md](CONTRIBUTING.md)

- 커밋: `<type>: <Subject>`
- MR 설명의 `Resolves: S15P21D203-<번호>` 가 Jira 연동 트리거. 템플릿이 채워주므로 번호만 입력
- master 직접 push 시 미반영. 모든 작업 MR 경유

## 설정 관리

프로필별 설정·비밀값은 git 제외. 상세는 `.gitignore`.

- `src/main/resources/application-{local,secret,prod}.yml`
- `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.jks`
- 로컬 데이터는 `/data/`, `/logs/` (`src/` 밖)
