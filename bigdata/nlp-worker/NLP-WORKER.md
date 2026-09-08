# NLP Worker GPU 배포 요약

## 1. 로컬에서 Docker 이미지 빌드

프로젝트에서 NLP Worker 디렉토리로 이동한다.

```powershell
cd .\bigdata\nlp-worker
```

이미지 빌드:

```powershell
docker build -t nlp-worker:latest .
```

이미지를 tar 파일로 저장:

```powershell
docker save -o nlp-worker.tar nlp-worker:latest
```

생성된 `nlp-worker.tar`를 GPU 서버의 `~/nlp-worker/`로 옮긴다.

---

## 2. GPU 서버 디렉토리 구조

GPU 서버는 다음 구조로 관리한다.

```text
~/nlp-worker/
├─ models/
├─ data/
└─ nlp-worker.tar
```

필요하면 먼저 생성:

```bash
mkdir -p ~/nlp-worker/models
mkdir -p ~/nlp-worker/data
```

---

## 3. 언어 판별 모델 준비

현재 필요한 모델:

```text
lid.176.bin
```

위치:

```text
~/nlp-worker/models/lid.176.bin
```

없으면 다운로드:

```bash
cd ~/nlp-worker/models
wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
```

확인:

```bash
ls -lh ~/nlp-worker/models
```

---

## 4. GPU 서버에서 Docker 이미지 로드

```bash
cd ~/nlp-worker
docker load -i nlp-worker.tar
```

확인:

```bash
docker images
```

---

## 5. NLP Worker 실행

Kafka 주소를 실제 접속 가능한 주소로 설정해서 실행한다.

```bash
docker run -d \
  --name news-nlp-worker \
  --restart unless-stopped \
  -e KAFKA_BOOTSTRAP_SERVERS="<Kafka 주소>" \
  -e KAFKA_RAW_TOPIC="news.raw.v1" \
  -e KAFKA_ENRICHED_TOPIC="news.enriched.v1" \
  -e KAFKA_CONSUMER_GROUP="nlp-worker-v1" \
  -e NLP_BATCH_SIZE="32" \
  -v "$(pwd)/models:/app/models" \
  -v "$(pwd)/data:/app/data" \
  nlp-worker:latest
```

---

## 6. 실행 확인

컨테이너 확인:

```bash
docker ps
```

로그 확인:

```bash
docker logs -f news-nlp-worker
```

모델 마운트 확인:

```bash
docker exec news-nlp-worker ls -lh /app/models
```

raw archive 확인:

```bash
ls -lh ~/nlp-worker/data/raw
```

---

## 7. 코드 수정 후 재배포

로컬:

```powershell
cd .\bigdata\nlp-worker
docker build -t nlp-worker:latest .
docker save -o nlp-worker.tar nlp-worker:latest
```

새 `nlp-worker.tar`를 GPU 서버에 다시 옮긴다.

GPU 서버:

```bash
docker stop news-nlp-worker
docker rm news-nlp-worker

cd ~/nlp-worker
docker load -i nlp-worker.tar
```

이후 위의 `docker run` 명령으로 다시 실행한다.

모델과 `data/`는 Docker 이미지와 분리되어 있으므로 다시 받을 필요가 없다.

---

## 핵심 구조

```text
Docker image
→ 코드 + Python 라이브러리

~/nlp-worker/models
→ NLP 모델

~/nlp-worker/data
→ raw archive 등 저장 데이터
```

`.dockerignore`에는 모델이 이미지에 포함되지 않도록 다음을 둔다.

```dockerignore
models/
data/
__pycache__/
*.pyc
```

Git에도 모델을 올리지 않는다.

```gitignore
bigdata/nlp-worker/models/
bigdata/nlp-worker/data/raw/
```
