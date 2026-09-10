#!/usr/bin/env python3
"""톤 모델을 nlp-worker/models/ 에 내려받는다.

GPU 서버는 이미지에 가중치를 넣지 않고 models/ 를 마운트해 참조한다
(pipeline/language.py 의 lid.176.bin 과 같은 방식). 이 스크립트는 인터넷이
되는 곳에서 한 번 실행해 models/tone-teacher/ 를 만들어 두는 용도다.

  # 인터넷 되는 곳에서
  python scripts/download_tone_model.py

  # 결과를 GPU 서버로
  rsync -av nlp-worker/models/tone-teacher/ \
      <user>@<gpu-host>:~/nlp-worker/models/tone-teacher/

컨테이너 안에서는 /app/models/tone-teacher 로 보인다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_REPO = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# transformers 가 로드에 실제로 필요한 것만 받는다. 약 1.1GB.
ALLOW = ["config.json", "*.safetensors", "tokenizer*", "*.model", "*.json",
         "special_tokens_map.json", "sentencepiece*"]
# .bin 은 safetensors 가 있으면 불필요하다. 받으면 용량이 두 배가 된다.
IGNORE = ["*.bin", "*.h5", "*.msgpack", "*.onnx", "*.ot", "*.tflite"]

REQUIRED = ["config.json"]


def main() -> int:
    ap = argparse.ArgumentParser(description="톤 모델을 models/ 에 내려받는다")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="HuggingFace repo id")
    ap.add_argument("--name", default="tone-teacher",
                    help="models/ 아래 디렉터리 이름")
    ap.add_argument("--force", action="store_true", help="기존 디렉터리 삭제 후 재다운로드")
    args = ap.parse_args()

    target = MODELS_DIR / args.name
    if target.exists() and not args.force:
        if (target / "config.json").is_file():
            print(f"이미 존재한다: {target}\n  다시 받으려면 --force")
            return 0
        print(f"디렉터리가 있으나 config.json 이 없다: {target}\n  --force 로 재다운로드", file=sys.stderr)
        return 1
    if target.exists():
        shutil.rmtree(target)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub 가 필요하다: pip install huggingface_hub", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"다운로드: {args.repo} → {target}")
    snapshot_download(
        repo_id=args.repo,
        local_dir=str(target),
        allow_patterns=ALLOW,
        ignore_patterns=IGNORE,
    )

    missing = [f for f in REQUIRED if not (target / f).is_file()]
    if missing:
        print(f"필수 파일 누락: {missing}", file=sys.stderr)
        return 1

    # NLI 라벨 순서를 여기서 미리 확인해 둔다. 서버에서 로그로 또 확인하지만,
    # 하드코딩 사고를 막는 값이라 눈으로 두 번 보는 편이 낫다.
    import json
    cfg = json.loads((target / "config.json").read_text(encoding="utf-8"))
    id2label = {int(k): str(v) for k, v in (cfg.get("id2label") or {}).items()}
    print(f"\nid2label = {id2label}")
    lowered = {i: v.lower() for i, v in id2label.items()}
    ent = next((i for i, v in lowered.items() if "entail" in v), None)
    con = next((i for i, v in lowered.items() if "contra" in v), None)
    if ent is None or con is None:
        print("경고: entailment/contradiction 라벨을 찾지 못했다. NLI 모델이 아닐 수 있다.",
              file=sys.stderr)
        return 1
    print(f"  entailment={ent}  contradiction={con}")

    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"\n완료: {target}  ({size / 1e9:.2f} GB)")
    print("GPU 서버로 복사:")
    print(f"  rsync -av {target}/ <user>@<gpu-host>:~/nlp-worker/models/{args.name}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
