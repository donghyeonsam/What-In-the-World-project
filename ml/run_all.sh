#!/usr/bin/env bash
# 전체 파이프라인. 어느 단계든 실패하면 멈춘다.
# 중간에 끊겼으면 그냥 다시 실행 — label 은 완료된 샤드를 건너뛴다.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"   # NLP worker 가 GPU0 사용

step() { echo; echo "================ $1 ================"; }

step "0. 정제";              python -m distill.prepare
step "0.4 centroid";          python -m distill.build_centroid
step "0.5 분야 배정";         python -m distill.assign_field
step "1. teacher 톤 라벨링";  python -m distill.label
step "2. 분할 + 교차표";      python -m distill.split
step "3. 톤 student × 5";     python -m distill.train_tone
step "4. 리포트";             python -m distill.evaluate
