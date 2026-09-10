# GPU 서버 NLP Worker 수동 배포 및 실행 가이드

> 대상: SSAFY GPU 서버에서 `~/nlp-worker`의 NLP Worker를 다시 실행할 때 사용하는 절차  
> 현재 방식: Docker 미사용 / Python `venv` 직접 실행 / SSH Local Port Forwarding 사용


# 0. 수동 배포 — 소스 압축 → GPU 서버 이동 → 해제

> Docker를 사용할 수 없는 GPU 서버에서는 `bigdata/nlp-worker` 소스 자체를 압축해서 옮긴 뒤 Python 가상환경으로 실행한다.  
> 기존 GPU 서버의 `models/`, `data/`는 유지하고, 소스 코드만 갱신하는 방식이다.

## 0-1. Windows 로컬에서 NLP Worker 소스 압축

Windows CMD 또는 PowerShell에서 프로젝트의 `bigdata/nlp-worker` 디렉토리로 이동한다.

예:

```cmd
cd C:\Users\SSAFY\Desktop\park\what_in_the_world\S15P21D203\bigdata\nlp-worker
```

그다음 소스만 압축한다.

```cmd
tar -czf nlp-worker-src.tar.gz --exclude=models --exclude=data --exclude=.venv --exclude=nlp-worker.tar --exclude=nlp-worker-src.tar.gz .
```

압축 파일 확인:

```cmd
dir nlp-worker-src.tar.gz
```

이 방식에서는 다음과 같은 소스/설정 파일들이 압축된다.

```text
main.py
config.py
consumer.py
producer.py
requirements.txt
pipeline/
storage/
resources/
Dockerfile
docker-compose.gpu.yml
NLP-WORKER.md
...
```

반면 다음은 제외한다.

```text
models/
data/
.venv/
nlp-worker.tar
nlp-worker-src.tar.gz
```

`models/`와 `data/`를 제외하는 이유는 GPU 서버에 이미 존재하는 대용량 모델 캐시와 처리 데이터를 덮어쓰지 않기 위해서다.

---

## 0-2. `nlp-worker-src.tar.gz`를 GPU 서버로 이동

Jupyter 파일 업로드 기능이나 사용 가능한 파일 전송 도구를 이용해서 다음 위치에 올린다.

```text
~/nlp-worker/nlp-worker-src.tar.gz
```

GPU 서버에서 확인:

```bash
cd ~/nlp-worker
ls -lh nlp-worker-src.tar.gz
```

---

## 0-3. GPU 서버에서 압축 해제

`~/nlp-worker`에서 그대로 해제한다.

```bash
cd ~/nlp-worker
tar -xzf nlp-worker-src.tar.gz
```

해제 후 확인:

```bash
ls -lah
```

대략 다음 구조가 보여야 한다.

```text
~/nlp-worker/
├── main.py
├── config.py
├── consumer.py
├── producer.py
├── requirements.txt
├── pipeline/
├── storage/
├── resources/
├── models/
├── data/
├── .venv/
├── .env
├── libhostoverride.so
└── nlp-worker-src.tar.gz
```

기존의 다음 항목들은 그대로 유지한다.

```text
models/
data/
.venv/
.env
libhostoverride.so
```

---

## 0-4. 소스 갱신 후 requirements가 바뀌었을 때

`requirements.txt`가 변경되지 않았다면 매번 재설치할 필요는 없다.

의존성이 추가되거나 변경되었을 때만:

```bash
cd ~/nlp-worker
source .venv/bin/activate
pip install -r requirements.txt
```

현재 GPU 서버에서는 PyTorch가 CUDA 12.8 호환 버전으로 맞춰져 있으므로, `requirements.txt`의 단순한 `torch` 항목 때문에 다른 CUDA 빌드가 다시 설치되지 않도록 주의한다.

현재 정상 확인된 PyTorch 환경:

```text
torch: 2.9.0+cu128
CUDA: True
CUDA version: 12.8
GPU: NVIDIA H200 NVL
```

---

## 0-5. 배포 파일 정리

압축 해제 및 실행 확인이 끝났다면 업로드용 압축 파일은 필요할 때만 보관하면 된다.

삭제하려면:

```bash
rm ~/nlp-worker/nlp-worker-src.tar.gz
```

이 명령은 압축 파일만 삭제하며, 해제된 프로젝트 소스에는 영향을 주지 않는다.

---


## 0. 현재 구성

```text
GPU 서버 NLP Worker
    ↓
127.0.0.1:19092
    ↓
SSH Local Port Forwarding
    ↓
EC2 B 172.26.11.46:19092
    ↓
Kafka
```

Kafka metadata가 `j15d203a.p.ssafy.io:19092`를 반환하므로, GPU 서버에서는 `libhostoverride.so`를 `LD_PRELOAD`로 적용해 해당 호스트명을 `127.0.0.1`로 해석하게 한다.

EC2 B의 Kafka 설정은 변경하지 않는다.

---

# 서버 재실행 후 매번 해야 하는 것

## 1. 터미널 1 — Kafka SSH 터널 실행

```bash
ssh -i ~/ec2_server_key/J15D203T.pem \
  -N \
  -L 19092:172.26.11.46:19092 \
  ubuntu@j15d203a.p.ssafy.io
```

정상이면 아무 출력 없이 실행 상태를 유지한다.  
**이 터미널은 닫지 않는다.**

## 2. 터미널 2 — 터널 확인

```bash
nc -vz -w 3 127.0.0.1 19092
```

정상 예시:

```text
Connection to 127.0.0.1 19092 port [tcp/*] succeeded!
```

## 3. NLP Worker 디렉토리 이동

```bash
cd ~/nlp-worker
```

## 4. 가상환경 활성화

```bash
source .venv/bin/activate
```

정상이면 프롬프트 앞에 `(.venv)`가 표시된다.

## 5. 환경변수 로드

```bash
set -a
source .env
set +a
```

확인:

```bash
echo $KAFKA_BOOTSTRAP_SERVERS
```

정상 값:

```text
127.0.0.1:19092
```

현재 `.env` 주요 값:

```env
KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:19092
KAFKA_RAW_TOPIC=news.raw.v1
KAFKA_ENRICHED_TOPIC=news.enriched.v1
KAFKA_CONSUMER_GROUP=nlp-worker-v1
NLP_BATCH_SIZE=32
HF_HOME=/home/j-j15d203/nlp-worker/models/huggingface
```

## 6. NLP Worker 실행

```bash
LD_PRELOAD=$PWD/libhostoverride.so python main.py
```

정상 동작 예:

```text
INFO:__main__:NLP Worker started; sentiment uses fixed dummy score 50.0
INFO:__main__:Batch committed: consumed=32 enriched=32 invalid=0
```

일부 잘못된 기사가 있으면 다음처럼 나올 수 있다.

```text
Batch committed: consumed=32 enriched=31 invalid=1
```

---

# 가장 짧은 실행 순서

## 터미널 1

```bash
ssh -i ~/ec2_server_key/J15D203T.pem \
  -N \
  -L 19092:172.26.11.46:19092 \
  ubuntu@j15d203a.p.ssafy.io
```

## 터미널 2

```bash
cd ~/nlp-worker
source .venv/bin/activate

set -a
source .env
set +a

nc -vz -w 3 127.0.0.1 19092

LD_PRELOAD=$PWD/libhostoverride.so python main.py
```

---

# 종료 방법

NLP Worker 종료:

```text
Ctrl + C
```

SSH 터널 종료:

```text
Ctrl + C
```

---

# 재부팅 후 다시 설치할 필요가 없는 것

`~/nlp-worker` 디렉토리가 유지된다면 일반적으로 다음은 다시 설치하지 않아도 된다.

- `.venv`
- PyTorch
- `protobuf`
- `tiktoken`
- fastText 관련 패키지
- E5 모델 캐시
- GLiNER 모델 캐시
- `models/lid.176.bin`
- `libhostoverride.so`

즉 서버 재부팅 후에는 **SSH 터널 재생성 → venv 활성화 → `.env` 로드 → Worker 실행**만 하면 된다.

---

# 문제 발생 시 확인

## Kafka 터널

```bash
nc -vz -w 3 127.0.0.1 19092
```

## Kafka metadata

```bash
cd ~/nlp-worker
source .venv/bin/activate

LD_PRELOAD=$PWD/libhostoverride.so python - <<'PY'
from confluent_kafka.admin import AdminClient

admin = AdminClient({
    "bootstrap.servers": "127.0.0.1:19092"
})

md = admin.list_topics(timeout=10)

print("Kafka metadata OK")

for broker_id, broker in md.brokers.items():
    print(f"broker id={broker_id}, host={broker.host}, port={broker.port}")

for topic in sorted(md.topics):
    print(topic)
PY
```

정상이라면 최소 다음 토픽들이 보여야 한다.

```text
news.raw.v1
news.enriched.v1
news.event.v1
news.unclassified.v1
```

## GPU 확인

```bash
source ~/nlp-worker/.venv/bin/activate

python - <<'PY'
import torch

print("torch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
print("CUDA version:", torch.version.cuda)
print("GPU count:", torch.cuda.device_count())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
PY
```

현재 정상 환경 기준:

```text
torch: 2.9.0+cu128
CUDA: True
CUDA version: 12.8
GPU count: 2
GPU: NVIDIA H200 NVL
```

---

# 현재 주의사항

현재 sentiment는 실제 모델이 아니라 고정 dummy 값이다.

```json
{
  "score": 50.0
}
```

GLiNER 처리 중 다음 경고가 반복될 수 있다.

```text
Sentence of length ... has been truncated to 384
```

이 경고 자체는 Worker 실패를 의미하지 않는다. 실제로 다음 로그가 계속 찍히는지가 중요하다.

```text
Batch committed: consumed=32 enriched=32 invalid=0
```

---

# 한 줄 요약

```text
SSH Kafka 터널 실행
→ .venv 활성화
→ .env 로드
→ LD_PRELOAD 적용
→ python main.py
```