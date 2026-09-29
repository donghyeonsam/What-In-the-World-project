# spark 이슈 클러스터링 테마별 분산 테스트 매뉴얼

Spark Master 없이 여러 노트북 VM이 동일한 JSONL을 각자 읽고, 미리 할당된
서로 다른 테마만 클러스터링한다. 운영 Spark/HDFS/Kafka/DB/GMS는 사용하지
않는다. 각 VM 내부에서는 Python multiprocessing으로 담당 테마를 병렬 처리한다.

이 문서는 다음 세 구성을 비교하는 예비 성능 테스트 절차다.

- 단일 노드: `laptop-a`
- 분산 2노드: `laptop-a`, `laptop-b`
- 분산 4노드: `laptop-a`, `laptop-b`, `laptop-c`, `laptop-d`

각 구성은 50K, 100K, 150K, 200K 입력을 워밍업 없이 한 번씩(`run-1`) 실행한다.
따라서 측정 시간에는 컨테이너와 Python 라이브러리의 초기 실행 비용이 포함된다.

```text
공통 입력 JSONL + 구성별 assignment JSON
├─ laptop-a: 할당 테마 + 로컬 multiprocessing
├─ laptop-b: 할당 테마 + 로컬 multiprocessing
├─ laptop-c: 할당 테마 + 로컬 multiprocessing
└─ laptop-d: 할당 테마 + 로컬 multiprocessing

결과 JSON 수집 → 구성별 무결성 검증 → 비교표
```

여기서 `laptop-a`는 파일 준비와 결과 취합을 담당하는 노트북이면서 계산에도
참여하는 worker다. Spark Master가 아니다. 계산 중 VM 간 네트워크 통신은
없으므로 브리지 네트워크나 Spark 포트 설정은 필수가 아니다. 파일 전달과 결과
수집만 할 수 있으면 되며, 공통 시작 시각을 사용하므로 VM의 시스템 시간은
동기화되어 있어야 한다.

## 역할 구분

### 마스터 노트북 겸 worker: `laptop-a`

`laptop-a`는 실시간으로 다른 worker를 제어하거나 작업을 배정하는 Spark
Master가 아니다. 테스트 준비와 진행 관리 역할을 맡으면서 실제 클러스터링
계산에도 참여한다.

- GitLab의 최신 코드를 받고 Docker 이미지를 한 번 빌드한다.
- 원본 200K JSONL을 50K, 100K, 150K, 200K로 나눈다.
- 단일·2노드·4노드 assignment를 생성한다.
- Docker 이미지, 입력 JSONL, assignment를 다른 노트북에 전달한다.
- 매 분산 회차의 공통 `START_AT`을 정해 참여자에게 전달한다.
- 단일 노드 테스트를 혼자 실행한다.
- 2노드와 4노드 분산 테스트에서는 worker로 함께 실행한다.
- 모든 worker의 결과 JSON을 취합하고 `comparison.md`를 생성한다.

### 그 외의 worker 노트북: `laptop-b`, `laptop-c`, `laptop-d`

일반 worker 노트북은 데이터 준비나 결과 병합을 하지 않고, 자신에게 배정된
테마만 클러스터링한다.

- GitLab의 최신 코드를 받는다.
- `laptop-a`가 전달한 Docker 이미지와 데이터 패키지를 설치한다.
- VM마다 서로 다른 `NODE_ID`를 설정한다.
- 2노드 테스트에서는 `laptop-b`까지만 참여한다.
- 4노드 테스트에서는 `laptop-b`, `laptop-c`, `laptop-d`가 모두 참여한다.
- 전달받은 `START_AT`과 동일한 실행 조건으로 명령을 실행한다.
- 생성된 결과 JSON을 `laptop-a`에 전달한다.
- 이미지 빌드, 데이터 분할, assignment 생성, 결과 병합은 하지 않는다.

### 모든 노트북의 공통 책임

- VM에 Docker Engine과 Docker Compose를 설치한다.
- 동일한 CPU·메모리·프로세스 제한을 사용한다.
- 시스템 시간이 동기화되어 있는지 확인한다.
- 동일한 Docker 이미지, 입력 JSONL, assignment를 사용한다.
- 자신의 `.env.node`에는 고유한 `NODE_ID`를 넣는다.
- 참여하는 분산 회차에서는 시작 시각 전에 명령을 실행한다.

| 작업 | `laptop-a` | `laptop-b` | `laptop-c` | `laptop-d` |
|---|:---:|:---:|:---:|:---:|
| 이미지·데이터·assignment 준비 | O | X | X | X |
| 단일 노드 실행 | O | X | X | X |
| 2노드 분산 실행 | O | O | X | X |
| 4노드 분산 실행 | O | O | O | O |
| 결과 JSON 전달 | 자체 취합 | O | O | O |
| 비교표 생성 | O | X | X | X |

## 1. 모든 노트북: 공통 준비

모든 VM에서 저장소의 최신 `develop` 브랜치를 받는다.

```bash
git clone https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21D203.git ~/S15P21D203
cd ~/S15P21D203
git switch develop
git pull --ff-only origin develop

docker --version
docker compose version
timedatectl show -p NTPSynchronized
date -u
```

공정한 비교를 위해 모든 VM의 Docker CPU, 메모리, 프로세스 수를 동일하게
설정한다. 이 문서의 기본값은 VM당 CPU 2코어, 메모리 4GB, 프로세스 2개다.

## 2. `laptop-a`: 이미지 빌드 / 모든 노트북: 이미지 로드

파일 준비를 담당하는 `laptop-a`에서 한 번 빌드한다.

```bash
mkdir -p ~/witw-benchmark/package
cd ~/S15P21D203/bigdata

docker build -f benchmark/Dockerfile -t witw-clustering-benchmark:1 .
docker save witw-clustering-benchmark:1 \
  | gzip > ~/witw-benchmark/package/witw-clustering-benchmark-1.tar.gz
```

생성한 `witw-clustering-benchmark-1.tar.gz`를 테스트에 참여하는 모든 VM에
전달하고 각 VM에서 로드한다.

```bash
docker load -i ~/Downloads/witw-clustering-benchmark-1.tar.gz
docker image inspect witw-clustering-benchmark:1 --format '{{.Id}}'
```

압축파일 SHA-256과 이미지 ID의 수동 비교는 선택 사항이다. 이후 worker와 결과
병합기가 입력 파일, assignment 및 결과의 일관성을 검증한다.

## 3. `laptop-a`: 네 입력 파일 생성

`laptop-a`에서 원본 200K JSONL을 네 개의 누적 입력으로 나눈다.

```bash
mkdir -p ~/witw-benchmark/data
cd ~/S15P21D203/bigdata

python3 benchmark/apps/prepare_datasets.py \
  /path/to/silver-200k-source.jsonl \
  ~/witw-benchmark/data
```

다음 파일이 생성된다.

```text
silver-050000.jsonl
silver-100000.jsonl
silver-150000.jsonl
silver-200000.jsonl
manifest.json
```

## 4. `laptop-a`: 단일·2노드·4노드 assignment 생성

`laptop-a`에서 각 입력에 대해 구성별 assignment를 만든다. 노드 수가 바뀌면
테마 배치도 달라지므로 2노드용과 4노드용 파일을 따로 사용해야 한다.

```bash
cd ~/S15P21D203/bigdata

for size in 050000 100000 150000 200000
do
  python3 benchmark/apps/make_assignments.py \
    ~/witw-benchmark/data/silver-${size}.jsonl \
    ~/witw-benchmark/data/assignment-single-${size}.json \
    --mode single \
    --nodes laptop-a

  python3 benchmark/apps/make_assignments.py \
    ~/witw-benchmark/data/silver-${size}.jsonl \
    ~/witw-benchmark/data/assignment-distributed-2nodes-${size}.json \
    --mode distributed \
    --nodes laptop-a laptop-b

  python3 benchmark/apps/make_assignments.py \
    ~/witw-benchmark/data/silver-${size}.jsonl \
    ~/witw-benchmark/data/assignment-distributed-4nodes-${size}.json \
    --mode distributed \
    --nodes laptop-a laptop-b laptop-c laptop-d
done
```

할당기는 테마 기사 수의 제곱을 예상 비용으로 사용해 큰 테마부터 부하가 가장
작은 노드에 배치한다. 한 테마는 항상 하나의 노드에만 배정된다.

## 5. `laptop-a`: 패키지 생성 / 모든 노트북: 압축 해제

`laptop-a`에서 입력과 assignment를 하나로 묶는다.

```bash
tar -czf ~/witw-benchmark/package/benchmark-data.tar.gz \
  -C ~/witw-benchmark/data .
```

이 파일을 모든 VM에 전달한 후 압축을 해제한다.

```bash
mkdir -p \
  ~/witw-benchmark/data \
  ~/witw-benchmark/results/single \
  ~/witw-benchmark/results/2nodes \
  ~/witw-benchmark/results/4nodes
tar -xzf ~/Downloads/benchmark-data.tar.gz \
  -C ~/witw-benchmark/data
```

모든 VM은 동일한 네 JSONL과 모든 assignment 파일을 가지고 있어야 한다.

## 6. 모든 노트북: VM별 설정

각 VM에서 설정 파일을 만든다.

```bash
cd ~/S15P21D203/bigdata/benchmark
cp node.env.example .env.node
```

공통 설정 예시는 다음과 같다.

```dotenv
BENCHMARK_IMAGE=witw-clustering-benchmark:1

BENCHMARK_DATA_DIR=/home/user/witw-benchmark/data
BENCHMARK_RESULTS_DIR=/home/user/witw-benchmark/results/single

WORKER_CPUS=2
WORKER_MEMORY=4g
WORKER_PROCESSES=2

MIN_CLUSTER_SIZE=8
MIN_SAMPLES=4
MIN_MEMBERSHIP_CONFIDENCE=0.8
MIN_CENTROID_SIMILARITY=0.92
```

`/home/user`는 각 VM에서 `echo "$HOME"`으로 확인한 실제 홈 경로로 바꾼다.
`NODE_ID`만 VM마다 고유하게 설정한다.

```text
laptop-a VM: NODE_ID=laptop-a
laptop-b VM: NODE_ID=laptop-b
laptop-c VM: NODE_ID=laptop-c
laptop-d VM: NODE_ID=laptop-d
```

Compose 설정을 확인한다.

```bash
docker compose --env-file .env.node -f docker-compose.yml config
```

## 7. 모든 노트북: 공통 실행 규칙

실행에 앞서서, 모두가 동시에 실행을 할 수 있도록, 한 사람이 아래의 명령어로 기준 시간을 정하고 공유한다.

```bash
date -u -d '+1 minute' '+%Y-%m-%dT%H:%M:%SZ'
```

1분 안에 입력할 수 있도록 모든 참여자는 실행 명령을 미리 준비한다. 한 명이라도
시작 시각을 놓쳤다면 해당 값을 재사용하지 말고 새로운 1분 뒤 시각을 발급한다.

분산 실행에서는 해당 구성에 참여하는 모든 VM이 다음 값을 똑같이 사용해야 한다.

```text
INPUT_FILE
ASSIGNMENT_FILE
MODE
ROWS
RUN_ID=run-1
START_AT
클러스터링 옵션
```

서로 다른 값은 `NODE_ID`뿐이다. 모든 참여자가 시작 시각 전에 명령을 실행하면
worker가 대기하다가 `START_AT`에 계산을 시작한다. 이미 지난 `START_AT`은 다시
사용할 수 없다.

## 8. `laptop-a`만: 단일 노드 실행

단일 노드는 `laptop-a`에서만 실행한다. 아래는 50K 예시다.

```bash
cd ~/S15P21D203/bigdata/benchmark

INPUT_FILE=silver-050000.jsonl \
ASSIGNMENT_FILE=assignment-single-050000.json \
MODE=single \
ROWS=50000 \
RUN_ID=run-1 \
START_AT=<새로운 미래 UTC 시각> \
BENCHMARK_RESULTS_DIR=$HOME/witw-benchmark/results/single \
docker compose \
  --env-file .env.node \
  -f docker-compose.yml \
  run --rm benchmark-worker
```

같은 방법으로 100K, 150K, 200K를 각각 한 번 실행한다.

| 입력 | `INPUT_FILE` | `ASSIGNMENT_FILE` | `ROWS` |
|---:|---|---|---:|
| 50K | `silver-050000.jsonl` | `assignment-single-050000.json` | `50000` |
| 100K | `silver-100000.jsonl` | `assignment-single-100000.json` | `100000` |
| 150K | `silver-150000.jsonl` | `assignment-single-150000.json` | `150000` |
| 200K | `silver-200000.jsonl` | `assignment-single-200000.json` | `200000` |

## 9. `laptop-a`와 `laptop-b`: 분산 2노드 실행

`laptop-a`와 `laptop-b`에서 같은 명령을 같은 시작 시각 전에 실행한다. 각 VM의
`.env.node`에 있는 `NODE_ID`만 서로 다르다.

```bash
cd ~/S15P21D203/bigdata/benchmark

INPUT_FILE=silver-050000.jsonl \
ASSIGNMENT_FILE=assignment-distributed-2nodes-050000.json \
MODE=distributed \
ROWS=50000 \
RUN_ID=run-1 \
START_AT=<두 VM에 동일한 미래 UTC 시각> \
BENCHMARK_RESULTS_DIR=$HOME/witw-benchmark/results/2nodes \
docker compose \
  --env-file .env.node \
  -f docker-compose.yml \
  run --rm benchmark-worker
```

50K, 100K, 150K, 200K를 각각 한 번 실행한다.

| 입력 | `INPUT_FILE` | `ASSIGNMENT_FILE` | `ROWS` |
|---:|---|---|---:|
| 50K | `silver-050000.jsonl` | `assignment-distributed-2nodes-050000.json` | `50000` |
| 100K | `silver-100000.jsonl` | `assignment-distributed-2nodes-100000.json` | `100000` |
| 150K | `silver-150000.jsonl` | `assignment-distributed-2nodes-150000.json` | `150000` |
| 200K | `silver-200000.jsonl` | `assignment-distributed-2nodes-200000.json` | `200000` |

## 10. 모든 노트북: 분산 4노드 실행

`laptop-a`, `laptop-b`, `laptop-c`, `laptop-d`에서 같은 명령을 같은 시작 시각
전에 실행한다. 2노드용 assignment를 재사용하지 않고 4노드용을 사용한다.

```bash
cd ~/S15P21D203/bigdata/benchmark

INPUT_FILE=silver-050000.jsonl \
ASSIGNMENT_FILE=assignment-distributed-4nodes-050000.json \
MODE=distributed \
ROWS=50000 \
RUN_ID=run-1 \
START_AT=<네 VM에 동일한 미래 UTC 시각> \
BENCHMARK_RESULTS_DIR=$HOME/witw-benchmark/results/4nodes \
docker compose \
  --env-file .env.node \
  -f docker-compose.yml \
  run --rm benchmark-worker
```

50K, 100K, 150K, 200K를 각각 한 번 실행한다.

| 입력 | `INPUT_FILE` | `ASSIGNMENT_FILE` | `ROWS` |
|---:|---|---|---:|
| 50K | `silver-050000.jsonl` | `assignment-distributed-4nodes-050000.json` | `50000` |
| 100K | `silver-100000.jsonl` | `assignment-distributed-4nodes-100000.json` | `100000` |
| 150K | `silver-150000.jsonl` | `assignment-distributed-4nodes-150000.json` | `150000` |
| 200K | `silver-200000.jsonl` | `assignment-distributed-4nodes-200000.json` | `200000` |

## 11. 실행 횟수

워밍업과 반복 실행이 없으므로 비교 조건은 총 12회다.

| 구성 | 데이터 크기 | 측정 회차 |
|---|---|---:|
| 단일 노드 | 50K, 100K, 150K, 200K | 4회 |
| 분산 2노드 | 50K, 100K, 150K, 200K | 4회 |
| 분산 4노드 | 50K, 100K, 150K, 200K | 4회 |
| 합계 |  | 12회 |

한 번의 분산 회차는 참여 노트북들이 동시에 실행하는 하나의 테스트다. 실제
컨테이너 실행 횟수는 단일 4회, 2노드 분산 8회, 4노드 분산 16회로 총 28회다.

## 12. 일반 worker는 전달 / `laptop-a`는 결과 취합

`laptop-a`에 토폴로지별 결과 디렉터리를 만든다.

```bash
mkdir -p \
  ~/witw-benchmark/all-results/2nodes \
  ~/witw-benchmark/all-results/4nodes
```

`laptop-a` 자신의 결과를 복사한다.

```bash
cp ~/witw-benchmark/results/single/*-run-1-*.json \
  ~/witw-benchmark/all-results/2nodes/
cp ~/witw-benchmark/results/single/*-run-1-*.json \
  ~/witw-benchmark/all-results/4nodes/
cp ~/witw-benchmark/results/2nodes/*-run-1-*.json \
  ~/witw-benchmark/all-results/2nodes/
cp ~/witw-benchmark/results/4nodes/*-run-1-*.json \
  ~/witw-benchmark/all-results/4nodes/
```

각 VM의 `~/witw-benchmark/results/2nodes`와 `results/4nodes`에 생성된 JSON을
`laptop-a`로 전달한다. 단일 결과는 `results/single`에 생성된다. 파일명에
`NODE_ID`가 포함되므로 같은 회차의 여러 worker 결과를 함께 보관할 수 있다.

```text
single-50000-run-1-laptop-a.json
distributed-50000-run-1-laptop-a.json
distributed-50000-run-1-laptop-b.json
...
```

- `2nodes` 디렉터리: 단일 결과와 2노드 분산 결과
- `4nodes` 디렉터리: 같은 단일 결과의 복사본과 4노드 분산 결과

2노드와 4노드 분산 결과는 파일명이 같을 수 있으므로 실행할 때부터 서로 다른
결과 디렉터리를 사용해야 한다. 위 실행 명령의 `BENCHMARK_RESULTS_DIR` 값을
생략하지 않는다.

현재 병합기는 한 번에 하나의 분산 토폴로지를 단일 결과와 비교하므로 2노드와
4노드 결과를 같은 병합 명령에 넣지 않는다.

## 13. `laptop-a`: 비교표 생성

2노드 비교표를 생성한다.

```bash
cd ~/S15P21D203/bigdata

python3 benchmark/apps/merge_results.py \
  ~/witw-benchmark/all-results/2nodes/*-run-1-*.json \
  --output ~/witw-benchmark/all-results/2nodes/comparison.md
```

4노드 비교표를 생성한다.

```bash
python3 benchmark/apps/merge_results.py \
  ~/witw-benchmark/all-results/4nodes/*-run-1-*.json \
  --output ~/witw-benchmark/all-results/4nodes/comparison.md
```

병합기는 다음을 검증한다.

- 예정된 모든 노드의 결과가 도착했는지
- 모든 노드가 동일한 입력과 assignment를 사용했는지
- 테마가 노드 사이에 중복 배정되지 않았는지
- 단일과 분산의 클러스터 결과 체크섬이 같은지
- 클러스터링 파라미터가 같은지

전체 분산 시간은 공통 시작 시각부터 가장 늦게 끝난 노드까지다. 각 노드가 전체
JSONL을 읽고 담당 테마를 필터링하는 시간도 포함한다.

최종 산출물은 다음 두 파일이다.

```text
~/witw-benchmark/all-results/2nodes/comparison.md
~/witw-benchmark/all-results/4nodes/comparison.md
```

PPT에는 측정 조건을 다음과 같이 명시한다.

> 각 조건 1회 측정, 워밍업 없이 컨테이너 초기 실행 비용을 포함한 전체 처리 시간 기준
