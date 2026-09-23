# 운영 FE·BE 로그 및 Spring·DB 지표

## Spring·PostgreSQL 최소 모니터링

기존 Grafana를 재사용하고 Prometheus와 postgres-exporter만 추가한다.
앱 EC2의 `prod` Spring 및 `witw` DB만 대상으로 한다.

```text
Prometheus → witw-backend:9091/actuator/prometheus → Spring 지표
Prometheus → postgres-exporter:9187/metrics → postgres:5432/witw 통계
Grafana → Prometheus → WITW · Spring & PostgreSQL 대시보드
```

15초마다 수집하고 7일 보관한다. 9091·9187·9090은 호스트에 공개하지 않는다.
Prometheus만 기존 모니터링 네트워크와 `witw-app-network` 양쪽에 연결한다.
DB exporter는 운영 DB의 기존 계정과 `POSTGRES_PASSWORD`를 사용한다.
DB 이름·계정은 운영 Compose의 `POSTGRES_DB`(기본 `witw`), `POSTGRES_USER`, `POSTGRES_PASSWORD`를 따른다.
대시보드 DB 쿼리는 기본 DB 이름 `witw`를 사용하므로 별도 DB 이름을 사용하면 쿼리도 맞춘다.

1. 운영 백엔드를 재배포한다. Spring 이미지 재빌드와 postgres-exporter 시작이 필요하다.
2. `deploy-monitoring-prod`로 모니터링을 배포한다. Prometheus 및 대시보드 파일도 자동 복사한다.
3. 아래 SSH 터널로 기존 Grafana에 접속하고 `WITW · Spring & PostgreSQL`을 연다.

수동 실행 시 기존 환경변수가 준비된 상태에서 저장소 루트에서 실행한다.

```bash
docker compose --env-file /opt/witw-backend/.env -p witw-backend-prod -f backend/docker-compose.prod.yml up -d --build
docker compose --env-file /opt/witw-monitoring/.env -f infra/monitoring/docker-compose.yml up -d
```

대시보드 12개 패널: API 요청/초, 평균·p95 응답시간, 5xx 비율, JVM heap,
Hikari 커넥션 사용·대기·최대, DB 전체 연결 수(idle 포함), 커밋·롤백/초, 최근 5분 데드락,
EC2 CPU·메모리·디스크 사용률과 디스크 읽기·쓰기.
API 지표는 `/api/**`만 집계한다. 실제 API를 여러 번 호출한 뒤 1분 이상 기다린다.
요청이 없으면 응답시간·오류 비율은 비어 있을 수 있다. 데드락 증가는 구간 추정치라 소수일 수 있다.
개별 SQL 실행시간 및 DB 컨테이너 CPU·메모리는 이 구성에 포함하지 않는다.

Grafana Explore에서 Prometheus를 선택해 `up`의 backend/postgres가 모두 1인지 확인한다.
`pg_up`도 1이어야 실제 DB 연결이 정상이다. exporter 자체가 살아 있는 것과 구분한다.
지표가 비면 `docker compose -f backend/docker-compose.prod.yml logs postgres-exporter`로 연결 오류를 확인한다.
Prometheus 설정을 수정한 뒤에는 해당 서비스를 재시작한다.

설정 근거: [Spring Boot metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html),
[postgres-exporter](https://github.com/prometheus-community/postgres_exporter).

## 빅데이터 지표 조회

앱 Grafana의 `BigData / WITW 데이터 처리 현황`에서 기존 파이프라인 지표와
빅데이터 분산 EC2 CPU·메모리·디스크 사용률·디스크 읽기/쓰기, Spark 배치 시간 p95를 조회한다.
앱 Grafana가 빅데이터 Prometheus에 직접 질의하며 지표를 복제하지 않는다.

빅데이터 모니터링의 cAdvisor는 Collector, Kafka, Silver Writer, HDFS, Spark
컨테이너의 CPU·메모리 working set을 수집한다. 컨테이너 CPU 패널은 코어당
백분율이 아니라 빅데이터 분산 EC2 전체 vCPU 합계를 100%로 정규화한다. 호스트 CPU는 실제
workload와 하이퍼바이저 대기 시간인 steal을 분리해서 표시한다. cAdvisor의
8080 포트는 호스트에 공개하지 않고 모니터링 Docker 네트워크에서만 수집한다.

- 빅데이터 Prometheus: 기본 `172.26.11.46:9090` 바인딩. 변경 시 빅데이터 배포 환경 파일에 `PROMETHEUS_BIND_HOST`를 설정한다.
- 앱 Grafana: 기본 `http://172.26.11.46:9090`. 변경 시 `/opt/witw-monitoring/.env`에 `BIGDATA_PROMETHEUS_URL`을 설정한다.
- 기존 `MONITORING_BIND_HOST`는 빅데이터 Grafana 바인딩에만 적용한다.
- 빅데이터 분산 EC2 자원은 node-exporter가 Linux 호스트를 읽어서 제공한다.
- VPC 보안 그룹에서 앱 EC2 → 빅데이터 분산 EC2 TCP 9090 접근이 허용되어야 한다.

빅데이터 모니터링과 앱 모니터링을 모두 배포한다. CI가 공유 대시보드를 복사하므로
별도 대시보드 import는 필요 없다. 배포 디렉터리에서 수동 Compose 명령을 사용할 때는
`export BIGDATA_DASHBOARDS_PATH=/opt/witw-monitoring/grafana/bigdata`를 먼저 실행한다.
저장소에서 실행할 때는 기본 상대 경로로 같은 대시보드를 읽는다.

Grafana Explore에서 `Prometheus-BigData`를 선택하고 `up{job="node"}`가 1인지 확인한다.
`node_memory_MemTotal_bytes`가 빅데이터 분산 EC2 메모리와 맞는지도 확인한다.
수집 설정을 반영하려면 기존 빅데이터 Prometheus를 재시작한다.

## 기존 로그 수집 상세

FE·BE와 같은 Linux Docker 호스트에서 실행한다. 서로 다른 호스트라면 이 Compose를
그대로 양쪽에 실행하지 말고, 호스트별 Alloy와 중앙 Loki 연결 구성을 먼저 정한다.

```text
FE Nginx / BE Spring stdout·stderr
→ 해당 호스트 Docker Engine
→ docker.sock을 마운트한 Alloy
→ Loki (7일 보관)
→ Grafana Explore
```

## 구성

| 항목 | 설정 |
| --- | --- |
| 수집 대상 | `logging=enabled`, `env=prod`, `service=fe`, `be` 또는 `postgres` |
| Loki 라벨 | `service_name`, `env`, `host`, `container` |
| Grafana | 서버의 `127.0.0.1:3002` → 컨테이너 `3000` |
| Loki / Alloy | 호스트 포트 공개 없음 |
| Docker 원본 로그 | FE·운영 BE 및 모니터링 컨테이너당 `10m × 3개` |
| 영속 볼륨 | Alloy 읽기 위치, Loki 데이터·WAL·Compactor 상태, Grafana 설정 |

FE는 `.gitlab/ci/front.yml`의 기존 배포 명령에 라벨을 추가했다.
운영 FE·BE·PostgreSQL은 `logging=enabled`, `env=prod` 라벨로 수집한다.
BigData 로그는 빅데이터 호스트의 별도 Alloy가 전송한다. Valkey는 수집하지 않는다.
기존 컨테이너에는 설정이 소급 적용되지 않으므로 운영 FE·BE를 재배포해야 한다.

FE 로그는 Nginx 접근·오류 로그이며 브라우저 JavaScript 오류는 포함하지 않는다.
BE는 현재 콘솔 로그를 수집하고, 날짜로 시작하는 로그를 기준으로 최대 256줄의 스택 트레이스를 묶는다.
멀티라인 버퍼는 최대 3초 대기한다. 로그 형식을 바꾸면 `firstline`도 확인한다.
컨테이너 내부 파일에만 쓰는 로그는 수집하지 않는다.

## 서버 최초 설정

EC2에 환경 파일만 최초 1회 생성한다. 설정 파일과 컨테이너 배포는 이후 CI가 처리한다.

```bash
sudo install -d /opt/witw-monitoring
sudo touch /opt/witw-monitoring/.env
sudo chmod 600 /opt/witw-monitoring/.env
```

`/opt/witw-monitoring/.env`에 `LOG_HOST`와 `GRAFANA_ADMIN_PASSWORD`를 입력한다.
`$`, `#`가 들어 있는 값은 작은따옴표로 감싼다. `.env`는 Git에서 제외된다.
관리자 계정 환경변수는 Grafana 데이터베이스 최초 생성 시 적용되므로,
이후 비밀번호 변경은 Grafana에서 수행한다.

`master` 브랜치에서 `infra/monitoring/**`가 변경되면 `deploy-monitoring-prod`가
설정을 `/opt/witw-monitoring`에 복사하고 검증한 뒤 `docker compose up -d`를 실행한다.
같은 파이프라인의 운영 FE·BE 배포가 있으면 완료를 기다리고, Prometheus·Alloy를 재시작해 설정을 반영한다.
기존 Compose 프로젝트와 볼륨을 유지하므로 Grafana 설정과 과거 데이터는 보존된다.
새 지표에는 `env=prod` 라벨을 붙이고 대시보드는 이 라벨만 조회해 과거 dev 지표와 구분한다.
모니터링 전용 GitLab 변수가 `development-monitoring` 범위라면 `production-monitoring`에도 적용한다.

### 운영 로그와 지표 조회 범위

Grafana Explore의 Loki에서 `{env="prod"}`를 조회하면 운영 FE·BE·PostgreSQL과
중앙 Loki에 전송된 빅데이터 로그를 함께 볼 수 있다. `env`는 컨테이너 라벨이며 Git 브랜치를 자동 판별하지 않는다.
FE·BE는 앱 Alloy와 같은 Docker 호스트에서 실행되어야 한다.
빅데이터 EC2의 `LOKI_URL`은 앱 EC2의 Loki `/loki/api/v1/push`를 가리켜야 한다.
앱 EC2의 `LOKI_BIND_HOST`가 기본값 `127.0.0.1`이면 다른 EC2에서 접근할 수 없으므로
사설 IP로 설정하고 빅데이터 EC2에서 TCP 3100 접근을 허용해야 한다.

지표는 앱 `Prometheus`와 `Prometheus-BigData` 데이터소스로 나뉜다.
앱 지표는 `env="prod"`로 조회하지만 빅데이터 지표에는 현재 `env` 라벨이 없으므로
BigData 대시보드 또는 `Prometheus-BigData`의 `up`으로 확인한다.
FE는 Nginx 로그만 수집하며 브라우저 오류·프론트 성능 지표, Valkey 및 NLP GPU 워커는 이 수집 구성에 포함되지 않는다.

`depends_on`은 시작 순서만 지정한다. 초기 Loki 준비 중 Alloy에서 연결 오류가 잠시 날 수 있으나,
계속 반복되면 Loki 로그와 Grafana 데이터 소스 연결 상태를 확인한다.

관리자 PC에서 SSH 터널을 연다 (`USER`, `SERVER`를 실제 값으로 변경).

```bash
ssh -N -L 3002:127.0.0.1:3002 USER@SERVER
```

브라우저에서 `http://localhost:3002`에 접속해 설정한 계정으로 로그인한다.
Loki 데이터 소스는 자동 등록된다. 데이터 소스 화면에서 연결 테스트 후 Explore를 연다.

## 수집 검증

1. 변경 사항을 반영한 운영 FE·BE 배포 파이프라인을 실행한다.
2. 서버에서 다음 명령으로 라벨과 원본 로그를 확인한다.

```bash
docker ps --filter label=logging=enabled --filter label=env=prod
docker logs --tail=20 what-in-the-world-front
docker logs --tail=20 witw-backend
curl --fail http://127.0.0.1:3000/
curl --fail http://127.0.0.1:3000/api/v1/themes/by-field
```

3. Grafana Explore에서 시간 범위를 최근 15분으로 선택하고 조회한다.

```logql
{env="prod", service_name="fe"}
{env="prod", service_name="be"}
{env="prod", service_name="be"} |= "ERROR"
```

FE에서는 방금 발생한 요청을, BE에서는 시작 로그와 실제로 출력된 애플리케이션 로그를 확인한다.
API를 호출했다고 반드시 BE 요청 로그가 생기지는 않는다. 예외 로그가 발생하면 스택 트레이스가
같은 이벤트에 포함되는지 확인한다. `/healthz`는 기존 Nginx 설정상 접근 로그가 없다.

4. Alloy 재시작 후 새 요청 로그가 들어오는지 확인한다.

```bash
docker compose restart alloy
```

5. Loki·Grafana 재시작 후 기존 로그 조회와 로그인 설정 유지 여부를 확인한다.

```bash
docker compose restart loki grafana
```

6. 운영 FE·BE를 다시 배포한 뒤 새 컨테이너의 로그도 들어오는지 확인한다.
7. 7일 운영 후 오래된 로그 삭제와 디스크 사용량을 확인한다. 삭제는 Compactor 주기와
   2시간 삭제 지연에 따라 비동기로 수행되며, 7일 설정이 디스크 용량 상한을 의미하지는 않는다.

## 운영 시 알아둘 점

- Docker 소켓은 Alloy에만 마운트한다. `:ro`는 Docker API를 읽기 전용으로 제한하지 않으며,
  일반적인 rootful Docker에서는 소켓 접근이 호스트 root 수준 권한으로 이어질 수 있다.
- Loki에는 인증 계층이 없으므로 현재처럼 Docker 네트워크 안에서만 접근한다.
- Alloy는 Docker API로 로그를 읽는다. 지표를 수집하는 Prometheus만 앱 네트워크에도 연결한다.
- 읽기 위치 저장은 무손실 전송 보장이 아니다. 수집 전 컨테이너 삭제, 원본 로그 로테이션,
  장시간 전송 실패, 멀티라인 버퍼가 남은 상태의 종료 등으로 누락될 수 있다.
- Nginx URL 등 로그에 민감한 값이 포함될 수 있으므로 실제 수집 내용을 확인한다.
- 로그량과 디스크 여유를 보고 원본 로그 크기와 보관 기간을 조정한다.

중단할 때는 이 디렉터리에서 `docker compose down`을 실행한다.
볼륨은 유지된다. `down -v`는 저장된 로그와 Grafana 설정까지 삭제하므로 사용하지 않는다.

## 검증 범위와 참고

로컬에서 모니터링·운영 BE의 Compose 설정 검증을 수행했다.
로컬 Docker 엔진이 실행 중이지 않아 이미지 실행, Alloy/Loki 제품별 설정 검증,
실제 로그 유입과 재시작 검증은 위 서버 절차로 수행해야 한다.

- [Alloy Docker 수집](https://grafana.com/docs/alloy/latest/monitor/monitor-docker-containers/)
- [Loki 보관 정책](https://grafana.com/docs/loki/latest/operations/storage/retention/)
- [Alloy 1.19.2](https://github.com/grafana/alloy/releases/tag/v1.19.2)
- [Loki 3.7.7](https://github.com/grafana/loki/releases/tag/v3.7.7)
- [Grafana 13.2.1](https://github.com/grafana/grafana/releases/tag/v13.2.1)
