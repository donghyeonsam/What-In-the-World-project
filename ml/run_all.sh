#!/usr/bin/env bash
# 전체 단계 순차 실행. GPU 서버에서 돈다.
#   ./run_all.sh            전체
#   ./run_all.sh 500        --limit 500 검증 실행 (분야×언어 교차표 확보)
set -euo pipefail
cd "$(dirname "$0")"

LIMIT_ARG=""
if [[ $# -ge 1 ]]; then LIMIT_ARG="--limit $1"; fi

echo "=== [0] 정제"
python -m distill.prepare ${LIMIT_ARG}

echo "=== [1] teacher 라벨링 (가장 무거움. 중단되면 같은 명령으로 재개)"
python -m distill.label ${LIMIT_ARG}

echo "=== [2] train/val 분할"
python -m distill.split

echo "=== [3] 분야 분류기 → artifacts/category/ (+ centroid.npy)"
python -m distill.train_category

echo "=== [4] 톤 student 6개 → artifacts/tone/<CATEGORY>/"
python -m distill.train_tone

echo "=== [5] 평가"
python -m distill.evaluate

echo
echo "완료. 다음 할 일:"
echo "  - artifacts/category/centroid.npy 를 nlp-worker conf/ 로 복사"
echo "  - nlp-worker classifier.py 를 코사인 유사도 → 증류된 MLP 로 교체"
