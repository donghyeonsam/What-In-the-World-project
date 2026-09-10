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


## Worker 연결 상태 및 검증 범위

- consumer → raw archive → NLP → producer delivery 확인 → 배치 commit으로 연결한다.
- 원본 collector 필드를 보존하고 `nlp_worker_data`만 추가한다.
- `sentiment.score=50.0`은 실제 중립 분석이 아닌 고정 Dummy 값이다.
  실제 모델 연결 시 `pipeline/sentiment.py::analyze_sentiment(article)`를 교체한다.
- 입력 오류는 로그를 남기고 enriched를 만들지 않는다. 빈 제목, 지원하지 않는
  발행 국가, 필수 필드 오류, 잘못된 JSON은 invalid 처리한다.
- 유효 기사 모두의 broker delivery가 확인된 배치만 commit한다.
  invalid만 있는 배치도 archive 성공 후 commit한다.
- 추론/전송/delivery/timeout/archive 오류는 프로세스를 종료하며 해당 배치를
  commit하지 않는다. 재시작 시 중복 전송과 archive 중복을 허용한다(at-least-once).
- archive는 날짜별 append JSONL이다. 정상 JSON은 원래 데이터를 저장하고,
  디코딩 불가능한 입력은 원본 bytes의 base64 및 Kafka 위치를 저장한다.
  쓰기 후 flush/fsync를 확인한다. 디스크 쓰기 실패 시 부분 레코드가 남을 수 있으며
  Kafka offset은 진행하지 않는다. archive 자체의 중복 제거/원자적 배치 저장은 없다.
- delivery callback 오류와 미완료 건수를 검사한다. flush 대기 상한은 300초다.
  애플리케이션 수준 retry/backoff 및 partition별 부분 commit은 추가하지 않았다.
- E5는 모듈 로딩 시, fastText/GLiNER/catalog는 최초 사용 시 로드해 재사용한다.
  fastText 파일은 컨테이너 기준 `/app/models/lid.176.bin`에 있어야 한다.
- centroid, mean-centering, 분류 threshold, taxonomy 변경은 적용하지 않았다.
  catalog는 동일한 create_article_embedding(title=name, body=description)으로
  생성했다는 제공 정보를 기준으로 유지한다.

### 이번 로컬 검증

기존 테스트 파일이 없어 파일 생성 없이 inline Python unittest로 검증했다.
첫 16개, 확장 후 24개 테스트가 통과했다. 외부 모델, tokenizer, pycountry 국가
레지스트리, Kafka, 파일 I/O는 대역으로 대체했으며 실제 pipeline/consumer/producer/
archive 코드와 Spark article_event 변환 함수를 호출했다.

검증 범위: 다국어 결과 연결, 필드 보존, Spark score 계약, invalid 폐기,
모델/카탈로그 캐싱, 긴 입력 청킹/가중평균, 벡터 검사, delivery 성공/실패/timeout/
callback 누락, 배치 간 실패 격리, commit 오류, SIGTERM, archive 부분 쓰기/fsync 실패.
CPU/GPU 선택 분기만 대역으로 검증했으며 실제 장치 실행 성능 검증은 아니다.

기존 catalog 자기 매칭 68/68 및 invalid 벡터 4/4를 수정 전후 확인했다.
기존 embedding과 동일한 정상 입력 출력도 대역 기준으로 비교했다.
이는 실제 기사 분류 정확도가 아니다. 보고된 14/15 baseline의 테스트 파일을
찾지 못했으므로 해당 정확도 재측정은 미완료다.

**실제 GPU/Kafka 환경 검증 미완료.**

GPU 서버에서는 기존 모델 artifact/패키지, GPU 장치 전달, broker 연결을 준비하고
처리량 및 max.poll.interval 내 배치 완료 여부를 확인해야 한다.
Spark는 sentiment score만 전달하므로 Dummy와 실제 분석값을 하류에서 구분하지
못한다. 실제 모델 도입/운영 데이터 사용 전 이 제한을 고려해야 한다.
