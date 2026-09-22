#!/bin/bash
# vLLM 서버 기동 — 매일 프로세스가 정리된 뒤 이 스크립트 하나만 실행하면 된다.
#
# 포트를 잡기 전에 확인하는 것
#   이 GPU 서버는 세 팀이 함께 쓴다. 24시간마다 프로세스가 정리되므로, 그 공백에
#   다른 팀이 같은 포트를 잡을 수 있다. 그 상태로 워커를 켜면 우리 워커가 남의
#   서비스에 기사 본문을 보내고 그 응답을 번역 결과로 받는다. 에러가 안 나서
#   알아채기 어렵다.
#
#   그래서 기동 전에 포트 주인을 확인하고, 우리 것이 아니면 멈춘다.

set -u

PORT="${LLM_PORT:-18203}"
MODEL="${LLM_SERVE_MODEL:-Qwen/Qwen3.8-27B-FP8}"
NAME="${LLM_SERVE_NAME:-news-llm}"
GPU_FRACTION="${LLM_GPU_FRACTION:-0.30}"
MAX_LEN="${LLM_MAX_LEN:-8192}"
MAX_SEQS="${LLM_MAX_SEQS:-16}"
LOG="$HOME/vllm.log"

export HF_HOME="${HF_HOME:-$HOME/nlp-worker/models/huggingface}"
export CUDA_VISIBLE_DEVICES=0

echo "포트 $PORT / 모델 $MODEL / GPU $GPU_FRACTION"

# ---- 1. 이미 우리 서버가 떠 있나 -------------------------------------
if curl -sf -m 3 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | grep -q "\"$NAME\""; then
  echo "  이미 정상 동작 중입니다. 아무것도 하지 않습니다."
  exit 0
fi

# ---- 2. 포트를 누가 쓰고 있나 ----------------------------------------
if ss -tln 2>/dev/null | grep -q ":$PORT "; then
  echo
  echo "  [중단] 포트 $PORT 를 다른 프로세스가 쓰고 있습니다."
  ss -tlnp 2>/dev/null | grep ":$PORT "
  echo
  echo "  우리 vLLM 이 아닙니다(/v1/models 에 $NAME 이 없음)."
  echo "  다른 팀 서비스일 수 있으니 죽이지 마세요."
  echo "  LLM_PORT 를 다른 번호로 바꿔 다시 실행하고,"
  echo "  워커의 .env 에서 LLM_BASE_URL 도 같이 바꾸세요."
  exit 1
fi

# ---- 3. 기동 ----------------------------------------------------------
screen -wipe >/dev/null 2>&1
screen -S vllm -X quit >/dev/null 2>&1

screen -dmS vllm bash -c "
  source \$HOME/vllm-venv/bin/activate
  export HF_HOME='$HF_HOME'
  export CUDA_VISIBLE_DEVICES=0
  while true; do
    vllm serve '$MODEL' \
      --served-model-name '$NAME' \
      --gpu-memory-utilization $GPU_FRACTION \
      --max-model-len $MAX_LEN \
      --max-num-seqs $MAX_SEQS \
      --enable-prefix-caching \
      --host 127.0.0.1 --port $PORT >> '$LOG' 2>&1
    echo \"[\$(date)] vLLM 종료, 10초 후 재시작\" >> '$LOG'
    sleep 10
  done
"

echo "  기동 중... (27B 로드에 2~3분)"

# ---- 4. 준비될 때까지 대기 -------------------------------------------
for i in $(seq 1 90); do
  if curl -sf -m 3 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | grep -q "\"$NAME\""; then
    echo "  준비 완료 ($((i * 5))초)"
    echo
    grep -E "KV cache size|Maximum concurrency|quantization|Using .*FP8" "$LOG" | tail -5
    nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
    exit 0
  fi
  sleep 5
done

echo "  [실패] 90초 * 5 안에 준비되지 않았습니다. 로그를 보세요:"
tail -30 "$LOG"
exit 1
