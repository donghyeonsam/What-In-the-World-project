# 이슈 후보 클러스터링 벤치마크

운영 `bigdata/spark/apps/issue_clustering.py`의 HDBSCAN 로직을 별도 Docker 컨테이너에서 측정한다. 이 테스트는 Spark Master, Kafka, HDFS, DB, GMS를 실행하지 않는다. 각 VM은 동일한 JSONL을 읽고, 미리 배정된 테마만 Python multiprocessing으로 클러스터링한다.

비교 구성은 단일 노드(`laptop-a`), 2노드(`laptop-a`·`laptop-b`), 4노드(`laptop-a`·`laptop-b`·`laptop-c`·`laptop-d`)다. 구성마다 **동일한 20만 행 JSONL 한 파일로 한 번 실행**한다. VM마다 CPU 2개, 메모리 4GB, 작업 프로세스 2개를 사용한다.

## 측정 방식

`worker.py`는 입력을 한 번 순서대로 읽고, 유효한 고유 기사 수가 5만 건 늘 때마다 체크포인트를 남긴다. 각 체크포인트에서는 해당 노드에 배정된 테마의 **그때까지 모인 기사 전체를 다시 클러스터링**한다. HDBSCAN을 증분 업데이트하지 않는다. 입력 끝에서 마지막 구간이 5만 건 미만이면 남은 기사에 대한 체크포인트를 한 번 더 남긴다. 정확히 5만 건 배수로 끝나면 빈 체크포인트는 만들지 않는다.

| 체크포인트 | 추가로 읽은 고유 기사 | 다시 클러스터링하는 기사 |
|---:|---:|---|
| 50,000 | 1~50,000 | 누적 50,000건 중 담당 테마 |
| 100,000 | 50,001~100,000 | 누적 100,000건 중 담당 테마 |
| 150,000 | 100,001~150,000 | 누적 150,000건 중 담당 테마 |
| 200,000 | 150,001~200,000 | 누적 200,000건 중 담당 테마 |

체크포인트 기준은 **모든 테마의 유효한 고유 기사 수**다. 따라서 분산 구성의 모든 노드가 입력의 같은 지점에서 체크포인트를 찍지만, 각 노드의 `loaded_article_count`에는 자신에게 배정된 테마의 기사만 포함된다. 잘못된 행과 중복 기사 ID는 체크포인트 기사 수에서 제외된다.

- `interval_seconds`: 직전 체크포인트 이후 새 기사 읽기와 **누적 전체의 재클러스터링**에 걸린 시간. 추가 5만 건만 독립적으로 클러스터링한 시간이 아니다.
- `cumulative_seconds`: 실제 처리 시작부터 현재 체크포인트까지의 누적 시간.
- `load_seconds`: 해당 구간을 읽고 파싱하는 데 걸린 시간.
- `clustering_seconds`: 해당 시점에 모인 담당 테마 전체를 클러스터링한 시간.
- 최종 결과 JSON의 `pipeline_seconds`는 모든 체크포인트를 거친 전체 처리 시간이다. 최종 `load_seconds`와 `clustering_seconds`는 각 구간의 값을 합한 것이다.

입력 SHA-256 확인, `START_AT`까지의 대기, 컨테이너 및 Python 시작 비용은 `interval_seconds`·`cumulative_seconds`·`pipeline_seconds`에 포함되지 않는다. 체크포인트가 완료될 때마다 로그 한 줄을 디스크에 기록하고 flush한다. 첫 로그는 5만 건의 클러스터링이 끝난 뒤에 나타나므로 한동안 출력이 없을 수 있다.

## 1. VM 준비와 입력 파일

VM에는 Docker Engine만 필요하다. Python과 scikit-learn은 이미지 안에 있다. Ubuntu에서 Docker를 설치하지 않았다면:

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo docker info --format '{{.OSType}}'
```

마지막 명령에서 `linux`가 출력되는지 확인한다. 이후 명령은 Docker 그룹 설정 없이 사용할 수 있도록 `sudo docker`를 쓴다.

각 VM에 같은 JSONL을 `~/witw-benchmark/data/enriched_200k.jsonl`로 둔다. 아래 명령은 정확히 20만 행인 입력을 기준으로 한다. 파일명이 다르면 assignment 생성과 실행 명령의 입력 파일명을 모두 같은 이름으로 바꾼다.

```bash
mkdir -p "$HOME/witw-benchmark/data" \
  "$HOME/witw-benchmark/results/single" \
  "$HOME/witw-benchmark/results/2nodes" \
  "$HOME/witw-benchmark/results/4nodes"

wc -l "$HOME/witw-benchmark/data/enriched_200k.jsonl"
ls -lh "$HOME/witw-benchmark/data/enriched_200k.jsonl"
```

`--expected-rows`는 JSONL의 **물리적 행 수**이며 assignment의 `raw_rows`와 같아야 한다. 예시 입력은 유효한 고유 기사도 정확히 20만 건이므로 체크포인트가 네 개 생긴다.

## 2. Docker 이미지 빌드와 VM에 로드

**수정된 `benchmark/apps/worker.py`가 들어 있는 소스**로 이미지를 빌드한다. 저장소를 새로 복제한 경우에는 그 수정 사항도 포함되어 있는지 확인한다. 빌드 위치는 저장소의 `bigdata` 디렉터리다.

```bash
cd /path/to/S15P21D203/bigdata
docker build -f benchmark/Dockerfile -t witw-clustering-benchmark:1 .
docker save -o witw-clustering-benchmark-1.tar witw-clustering-benchmark:1
```

Docker를 실행하는 PC에서 빌드한 뒤 tar를 VM의 `/home/ubuntu/file/`로 전달해도 된다. VM에서 로드한다.

```bash
ls -lh "$HOME/file/witw-clustering-benchmark-1.tar"
sudo docker load -i "$HOME/file/witw-clustering-benchmark-1.tar"
sudo docker image inspect witw-clustering-benchmark:1 --format '{{.Id}}'
```

분산 테스트에서는 모든 VM에 같은 이미지와 같은 입력 JSONL을 사용한다. 이미지를 바꿨다면 모든 VM에 새 이미지를 다시 전달한다.

## 3. 테마 assignment 생성

assignment는 노드별 담당 테마, 입력 파일명·SHA-256, 전체 행 수와 테마별 기사 수를 담는다. 기사 본문이나 임베딩은 담지 않는다. `worker.py`는 실행 전 입력 파일과 assignment의 파일명·행 수·SHA-256을 확인한다.

`laptop-a`에서 이미지에 포함된 Python으로 구성별 assignment를 한 번씩 만든다. 같은 입력에 대한 파일이므로 필요한 분산 VM에도 전달한다.

```bash
sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$HOME/witw-benchmark/data:/benchmark/input" \
  witw-clustering-benchmark:1 \
  python3 /opt/benchmark/make_assignments.py \
  /benchmark/input/enriched_200k.jsonl \
  /benchmark/input/assignment-single-200000.json \
  --mode single --nodes laptop-a

sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$HOME/witw-benchmark/data:/benchmark/input" \
  witw-clustering-benchmark:1 \
  python3 /opt/benchmark/make_assignments.py \
  /benchmark/input/enriched_200k.jsonl \
  /benchmark/input/assignment-distributed-2nodes-200000.json \
  --mode distributed --nodes laptop-a laptop-b

sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$HOME/witw-benchmark/data:/benchmark/input" \
  witw-clustering-benchmark:1 \
  python3 /opt/benchmark/make_assignments.py \
  /benchmark/input/enriched_200k.jsonl \
  /benchmark/input/assignment-distributed-4nodes-200000.json \
  --mode distributed --nodes laptop-a laptop-b laptop-c laptop-d
```

단일 노드는 모든 테마를 `laptop-a`에 배정한다. 분산 구성에서는 테마별 기사 수의 제곱을 예상 비용으로 삼아 테마를 서로 다른 노드에 배정한다. 노드 수가 달라지면 배정도 달라지므로 2노드와 4노드 assignment를 구분한다. assignment를 만드는 동안 입력 전체를 읽고 SHA-256을 계산하므로 시간이 걸릴 수 있다.

## 4. 벤치마크 실행

아래는 **단일 노드**의 실제 실행 예다. `START_AT`은 미래 UTC 시각이어야 한다. worker가 먼저 입력 전체의 SHA-256을 검사하므로, 예시에서는 10분 뒤를 지정한다. 입력을 읽은 뒤 `READY`가 출력되면 지정 시각까지 대기한다.

```bash
node_id=laptop-a
mode=single
assignment_file=assignment-single-200000.json
result_group=single
start_at="$(date -u -d '+10 minutes' '+%Y-%m-%dT%H:%M:%SZ')"

mkdir -p "$HOME/witw-benchmark/results/$result_group"
echo "$start_at"

sudo docker run --rm \
  --user "$(id -u):$(id -g)" \
  --cpus=2 --memory=4g \
  -e OMP_NUM_THREADS=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  -e MKL_NUM_THREADS=1 \
  -e NUMEXPR_NUM_THREADS=1 \
  -v "$HOME/witw-benchmark/data:/benchmark/input:ro" \
  -v "$HOME/witw-benchmark/results/$result_group:/benchmark/results" \
  witw-clustering-benchmark:1 \
  python3 /opt/benchmark/worker.py \
  --node-id "$node_id" \
  --mode "$mode" \
  --expected-rows 200000 \
  --assignment "/benchmark/input/$assignment_file" \
  --input /benchmark/input/enriched_200k.jsonl \
  --output "/benchmark/results/$mode-200000-run-1-$node_id.json" \
  --start-at "$start_at" \
  --processes 2
```

분산 테스트에서는 **같은 실행 명령**을 각 참여 VM에서 실행하되, 위 첫 다섯 변수만 다음처럼 설정한다. `start_at`은 한 VM에서 충분히 미래인 UTC 시각을 정해 모든 참여 VM에 **동일한 문자열**을 전달한다. 각 VM에서 별도로 `date -d '+10 minutes'`를 계산하면 시작 시각이 어긋난다.

| 구성 | 실행 VM의 `node_id` | `mode` | `assignment_file` | `result_group` |
|---|---|---|---|---|
| 단일 | `laptop-a` | `single` | `assignment-single-200000.json` | `single` |
| 2노드 | `laptop-a`, `laptop-b` | `distributed` | `assignment-distributed-2nodes-200000.json` | `2nodes` |
| 4노드 | `laptop-a`, `laptop-b`, `laptop-c`, `laptop-d` | `distributed` | `assignment-distributed-4nodes-200000.json` | `4nodes` |

분산 VM의 시스템 시간을 동기화하고, 같은 입력 파일·이미지·assignment·`start_at`·클러스터링 파라미터를 사용한다. 각 VM은 입력 20만 행을 모두 읽으면서 자기에게 배정된 테마만 메모리에 모아 클러스터링한다. VM 사이의 통신이나 Spark Master는 없다. `laptop-a`도 계산에 참여한다.

구성당 한 번 실행하므로 총 **3회 테스트, 7개 컨테이너 실행**이다. 워밍업과 반복 측정은 포함하지 않는다.

## 5. 진행 상황과 결과 확인

실행 중에는 다음 메시지가 순서대로 출력된다.

```text
READY node=laptop-a themes=68 start_at=...
CHECKPOINT node=laptop-a articles=50000 interval=...s cumulative=...s
CHECKPOINT node=laptop-a articles=100000 interval=...s cumulative=...s
CHECKPOINT node=laptop-a articles=150000 interval=...s cumulative=...s
CHECKPOINT node=laptop-a articles=200000 interval=...s cumulative=...s
DONE node=laptop-a articles=200000 seconds=... output=...
```

`--rm`은 종료된 컨테이너만 제거한다. 호스트의 결과 디렉터리에 쓰인 파일은 남는다. 단일 노드 예시의 산출물은 다음 두 파일이다.

```text
~/witw-benchmark/results/single/single-200000-run-1-laptop-a.milestones.jsonl
~/witw-benchmark/results/single/single-200000-run-1-laptop-a.json
```

`.milestones.jsonl`은 체크포인트마다 즉시 한 줄씩 기록한다. 유효한 고유 기사 20만 건이면 4줄이다. 마지막 `.json`은 모든 체크포인트가 끝난 뒤 작성되며 최종 테마 결과, 처리 건수, 전체 시간을 담는다.

```bash
ls -lh "$HOME/witw-benchmark/results/single/"
wc -l "$HOME/witw-benchmark/results/single/single-200000-run-1-laptop-a.milestones.jsonl"
```

체크포인트별 읽기와 클러스터링 시간을 보려면 VM의 Python을 설치하는 대신 이미지 안의 Python으로 로그를 읽는다.

```bash
sudo docker run --rm -i witw-clustering-benchmark:1 python3 -c '
import json, sys
for line in sys.stdin:
    row = json.loads(line)
    print("articles=%d interval=%.3fs cumulative=%.3fs load=%.3fs clustering=%.3fs" % (
        row["checkpoint_articles"], row["interval_seconds"],
        row["cumulative_seconds"], row["load_seconds"],
        row["clustering_seconds"],
    ))
' < "$HOME/witw-benchmark/results/single/single-200000-run-1-laptop-a.milestones.jsonl"
```

`interval_seconds`는 각 구간의 경과 시간이고 `cumulative_seconds`는 누적 시간이다. 10만 건 구간의 `interval_seconds`에는 새 5만 건 읽기와 **누적 10만 건의 재클러스터링**이 포함된다. 10만 건을 처음부터 독립적으로 한 번 처리한 시간과는 다르다. 입력이 커지면 테마별 HDBSCAN 작업량도 커지므로 구간 시간이 대체로 늘 수 있지만, 테마별 분포와 VM 상태 때문에 단조 증가하지는 않는다.

## 6. 단일·분산 결과 비교

각 분산 VM의 **최종 `.json`**을 `laptop-a`로 모으고, 단일 결과와 함께 토폴로지별 디렉터리에 둔다. 체크포인트 `.milestones.jsonl`은 시간 분석용으로 따로 보관한다.

```text
~/witw-benchmark/all-results/2nodes/
  single-200000-run-1-laptop-a.json
  distributed-200000-run-1-laptop-a.json
  distributed-200000-run-1-laptop-b.json

~/witw-benchmark/all-results/4nodes/
  single-200000-run-1-laptop-a.json
  distributed-200000-run-1-laptop-a.json
  distributed-200000-run-1-laptop-b.json
  distributed-200000-run-1-laptop-c.json
  distributed-200000-run-1-laptop-d.json
```

`merge_results.py`는 최종 JSON을 읽어 노드 누락, 입력·assignment의 동일성, 테마 중복, 최종 클러스터 체크섬과 파라미터를 검증하고 `comparison.md`를 만든다. 호스트 Python이 없으면 이미지 안에서 실행할 수 있다.

```bash
sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$HOME/witw-benchmark/all-results/2nodes:/benchmark/results" \
  witw-clustering-benchmark:1 \
  sh -c 'python3 /opt/benchmark/merge_results.py /benchmark/results/*.json --output /benchmark/results/comparison.md'

sudo docker run --rm --user "$(id -u):$(id -g)" \
  -v "$HOME/witw-benchmark/all-results/4nodes:/benchmark/results" \
  witw-clustering-benchmark:1 \
  sh -c 'python3 /opt/benchmark/merge_results.py /benchmark/results/*.json --output /benchmark/results/comparison.md'
```

비교표에는 **20만 건 최종 결과 한 행**만 나온다. 현재 병합기는 `.milestones.jsonl`을 읽지 않으므로 5만·10만·15만 건의 분산 비교는 각 노드의 체크포인트 로그에서 같은 `checkpoint_articles`를 찾아 별도로 계산해야 한다. 분산 구성의 체크포인트 완료 시각은 참여 노드 중 가장 늦은 `finished_at_epoch`을 사용한다. 이 벤치마크는 각 노드가 전체 JSONL을 읽는 비용과 담당 테마의 반복 클러스터링 비용을 함께 측정한다.
