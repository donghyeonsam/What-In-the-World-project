# tone-distill v2 — 분야별 톤 분류기 증류 (5분야)

뉴스 기사의 논조를 0~100 점수로 내는 모델 5종을 만든다.
사람이 라벨을 달지 않는다. NLI teacher 가 라벨을 만들고 그것으로 student 를 증류한다.

## 구조

```
① 뉴스 수집기 → ② Kafka news.raw.v1 → ③ NLP worker → ...
                                          └─ 여기의 감성 분석 모델을 만든다
```

산출물 5개. NLP worker 가 정한 `field_id` 로 라우팅되어 하나만 실행된다.

```
work/models/tone/POLITICS/   encoder/ + head.pt + meta.json
                 ECONOMY/
                 SOCIETY/
                 TECH/
                 SPORTS/
```

## 모델

| 역할 | 모델 | 배포 |
|---|---|---|
| teacher | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | ✗ 라벨 생성만 |
| 분야 배정 | worker `pipeline/embedding.py` + `theme_catalog.json` | ✗ worker 것을 직접 호출 |
| **student ×5** | `jhu-clsp/mmBERT-small` 파인튜닝 | **✓** |

teacher 는 NLI(자연어 추론) 모델이다. "이 기사는 낙관적으로 서술한다" 같은
가설을 던져 entailment 확률을 받는 제로샷 방식으로 라벨을 만든다.
student 는 NLI 가 아니라 인코더 + `Linear(H, 2)` 회귀 모델이다.

## 왜 분야를 worker 분류기로 정하나

런타임에서 기사를 어느 톤 모델로 보낼지는 worker 가 정한다. 학습 데이터를
teacher 기준으로 나누면 두 기준이 달라져, 런타임에 "자기 같은 기사를 본 적 없는
모델" 에게 채점받는 기사가 생긴다. 같은 분류기를 양쪽에 쓰면 그 불일치가
정의상 사라진다.

그래서 임베딩도 베끼지 않는다. `worker_embed.py` 가 worker 의
`pipeline/embedding.py` 를 **파일째로 import** 한다. worker 는 제목을 모든
청크에 넣고 본문을 384 토큰씩 64 겹쳐 자른 뒤 가중 평균하는데, 본문을
한 번에 인코딩하면 다른 벡터가 나온다. 코드를 복사해 두면 worker 가 바뀔 때
조용히 어긋나므로 파일을 직접 읽는다.

`config.yaml` 의 `assign.worker_path` 하나가 임베딩·카탈로그·centroid 를
모두 worker 쪽에 맞춘다.

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export CUDA_VISIBLE_DEVICES=1        # NLP worker 가 GPU0 사용

# 데이터 준비 — 아카이브 여러 개를 하나로
python merge_archive.py ~/nlp-worker/data/raw/*.jsonl --out-dir data

# config.yaml 의 data.input, assign.catalog 확인 후
./run_all.sh
```

단계별로 돌리려면:

```bash
python -m distill.prepare                    # 정제
python -m distill.prepare --limit 5000       #   소규모 점검
python -m distill.build_centroid             # centroid (worker 쪽에 있으면 복사해 쓸 것)
python -m distill.assign_field --limit 2000  # 분야 배정 (먼저 소규모로 확인)
python -m distill.assign_field               # 전체
python -m distill.label --limit 500          # 라벨링 검증
python -m distill.label                      # 전체 (샤드 재개 지원)
python -m distill.split                      # 분할 + 교차표
python -m distill.train_tone                 # student 5종
python -m distill.train_tone --field ECONOMY # 하나만
python -m distill.evaluate                   # 리포트
```

## 설정에서 건드릴 것

`config.yaml` 하나만 고치면 된다.

| 키 | 의미 |
|---|---|
| `data.input` | 입력 JSONL. 단일 파일 / glob / 디렉터리 |
| `data.body_quality.min_body_chars` | 본문 하한. 얇은 칸이 많으면 300→200 |
| `data.domain_country_overrides` | 도메인 기준 국가 교정 (theguardian 오분류 대응) |
| `assign.worker_path` | **nlp-worker 루트.** 임베딩·카탈로그·centroid 가 여기 붙는다 |
| `assign.min_margin` | 1위-2위 마진 하한. 학습셋에만 적용 (0 = 미적용) |
| `teacher.batch_size` | GPU 메모리에 맞춰. H200 기준 384~768 |
| `student.gradient_checkpointing` | VRAM 남으면 `false` 가 30~40% 빠름 |
| `fields` | worker `field_id` 와 **반드시** 일치 |

## 중요한 전제 — 중심화 (E5 비등방성)

multilingual-e5 임베딩은 모든 벡터가 좁은 원뿔에 몰린다. 실측으로
`theme_catalog.json` 의 68개 테마는 서로 다른 분야끼리도 코사인 +0.84 이고,
1위와 2위의 마진 중앙값이 **0.0051** 이다. 분야 판정이 사실상 동전 던지기다.

코퍼스 평균(centroid)을 빼면 다른 분야끼리가 −0.04 로 내려가고 마진이
0.0510 이 된다. `assign_field` 가 시작 시 이 값을 진단한다.

```
||mean|| < 0.3   정상
||mean|| > 0.7   중심화 안 됨 → 분야 판정이 소수점 셋째 자리로 갈린다
```

**centroid 는 worker 와 같은 파일이어야 한다.** worker 쪽에
`resources/centroid.npy` 가 생기면 그것을 복사해 쓴다. 다른 centroid 를 쓰면
학습 때 나눈 분야와 런타임 라우팅이 어긋나, worker 분류기를 재사용한 이유가
사라진다.

```bash
cp ~/nlp-worker/resources/centroid.npy work/centroid.npy
```

worker 쪽 적용 방법은 별도 문서(`중심화_적용안_DB무변경.md`) 참고.

## 라벨 두 종류

- **학습 라벨** — teacher 가 100% 생성. 사람 개입 없음
- **검증 라벨** — 사람이 150~400건. **선택 사항.** 집계 방식 확정용
  (`choose_aggregate.py`)

## 설계 메모

- 출력은 `p_pos`, `p_neg` 두 확률. 라벨은 `scoring.py` 로직으로 판정한다.
  임계값은 학습 대상이 아니라 나중에 바꿔도 라벨링을 다시 돌릴 필요가 없다.
- `mixed` 와 `neutral` 은 `tone_point` 가 같을 수 있다(둘 다 ~51.5).
  **반드시 라벨을 점수와 함께 저장**해야 구분된다.
- 청크 집계는 `topk_mean`. `weighted_mean` 은 중립 청크가 많은 기사에서
  가설 기저율 비대칭이 누적돼 긍정 기사가 negative 로 뒤집힐 수 있다.
- 세 방식 값을 모두 `alt_agg` 에 저장하므로 나중에 teacher 재실행 없이 비교 가능.
