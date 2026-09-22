"""분야별 톤 점수 보정 기준표를 만든다 → models/tone-student/calibration.json

왜 필요한가
  student 가 내는 점수의 중앙값이 분야마다 크게 다르다(실측).

      POLITICS 22.6 · ECONOMY 42.3 · SOCIETY 51.8 · SPORTS 62.3 · TECH 88.5

  분야 안의 5~95% 폭이 60점대이므로, 분야 간 격차 66점은 "기사 내용"만큼
  점수를 좌우한다. 지구본이 논조가 아니라 그 나라 뉴스의 테마 구성을 그리게 된다.

왜 그냥 빼면 안 되는가
  score = 50 × (1 + p_pos − p_neg) 은 0~100 경계가 있다. 이미 위쪽에 붙어 있는
  TECH 분포를 −0.77 만큼 아래로 밀면 5~95% 구간이 27.3~98.9 에서 0~60.4 로
  뭉개진다. 중앙값 위 절반이 50~60 사이에 다 낀다. POLITICS 는 반대로 퍼져서
  정치 기사 대부분이 긍정으로 보인다.

무엇을 하는가
  분야마다 d = p_pos − p_neg 의 분위수 101개(0%~100%)를 구해 저장한다.
  서빙할 때는 np.interp 로 "이 기사가 같은 분야 기사 중 몇 퍼센타일인가"를
  찾아 그것을 0~100 점수로 쓴다. 분야 안 순서는 그대로, 경계 뭉개짐 없음.

기준표는 한 번 만들고 고정한다
  매번 다시 계산하면 "유난히 부정적인 주"가 항상 중앙값 50 으로 정규화되어
  변화가 사라진다. 고정해 두어야 실제로 부정적인 기간이 50 아래로 내려간다.
  코퍼스가 크게 바뀌었을 때만 다시 만든다.

실행 (GPU 서버, nlp-worker venv)
    cd ~/nlp-worker
    source .venv/bin/activate
    set -a; source .env; set +a
    python build_calibration.py --n 3000

    # 기존 표를 덮어쓸 때
    python build_calibration.py --n 3000 --force
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import logging
import os
import random
import sys
import time
import types
from pathlib import Path

import numpy as np

WORKER = Path(__file__).resolve().parent
DEFAULT_SRC = Path.home() / "tone-distill" / "work" / "clean.field.jsonl"
DEFAULT_OUT = WORKER / "models" / "tone-student" / "calibration.json"

FIELDS = {"POLITICS": 1, "ECONOMY": 2, "SOCIETY": 3, "TECH": 4, "SPORTS": 5}


def load_tone():
    """pipeline/__init__.py 를 거치지 않고 tone.py 만 올린다.

    거치면 GLiNER·E5·번역모델까지 다 로드된다. 여기서는 톤만 필요하다.
    """
    # 표를 만드는 동안에는 보정을 꺼 둔다. 이미 calibration.json 이 있는 상태에서
    # 다시 돌릴 때 보정된 값 위에 또 보정이 얹히지 않게 하기 위함이다.
    # (p_pos/p_neg 자체는 보정과 무관하지만, 의도를 코드로 못박아 둔다.)
    os.environ["TONE_CALIBRATION"] = "0"

    pkg = types.ModuleType("pipeline")
    pkg.__path__ = [str(WORKER / "pipeline")]
    sys.modules["pipeline"] = pkg
    spec = importlib.util.spec_from_file_location(
        "pipeline.tone", str(WORKER / "pipeline" / "tone.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["pipeline.tone"] = m
    spec.loader.exec_module(m)
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC),
                    help="tone-distill 의 work/clean.field.jsonl")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--n", type=int, default=3000, help="분야당 표본 수")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="기존 표를 덮어쓴다")
    args = ap.parse_args()

    logging.disable(logging.INFO)

    out = Path(args.out)
    if out.exists() and not args.force:
        sys.exit(f"이미 있습니다: {out}\n"
                 f"  기준표는 고정해서 쓰는 것이 원칙입니다. "
                 f"정말 다시 만들려면 --force 를 붙이세요.")

    src = Path(args.src).expanduser()
    if not src.exists():
        sys.exit(f"입력 파일이 없습니다: {src}")

    print(f"입력  {src}")
    by_field: dict[int, list] = collections.defaultdict(list)
    for line in src.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        fid = r.get("field_id")
        if fid in FIELDS.values():
            by_field[fid].append(r)
    print("  " + "  ".join(f"{f}={len(by_field[i]):,}" for f, i in FIELDS.items()))

    tone = load_tone()
    scorer = tone.get_tone_scorer()
    if scorer is None:
        sys.exit("톤 모델이 로드되지 않았습니다. smoke_student.py 로 먼저 확인하세요.")
    print(f"  backend={type(scorer).__name__} "
          f"device={getattr(scorer, 'device', '?')}\n")

    grid = list(range(101))                      # 0% ~ 100%
    quantiles: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    started = time.time()

    for name, fid in FIELDS.items():
        rows = by_field.get(fid, [])
        if len(rows) < 200:
            sys.exit(f"{name} 표본이 {len(rows)}건뿐입니다. 기준표를 만들 수 없습니다.")
        rng = random.Random(args.seed)
        sample = rng.sample(rows, min(args.n, len(rows)))

        d = np.empty(len(sample), dtype=np.float64)
        for i, r in enumerate(sample):
            res = tone.score_article({"title": r.get("title"), "body": r.get("body")},
                                     field_id=fid)
            d[i] = res["p_pos"] - res["p_neg"]
            if (i + 1) % 500 == 0:
                print(f"  {name:<9} {i + 1:>6,}/{len(sample):,}  "
                      f"({time.time() - started:.0f}s)", flush=True)

        q = np.percentile(d, grid)
        quantiles[name] = [round(float(x), 6) for x in q]
        counts[name] = len(sample)
        raw = 50.0 * (1.0 + d)
        print(f"  {name:<9} n={len(sample):,}  "
              f"보정 전 중앙값 {np.median(raw):.1f} "
              f"(5% {np.percentile(raw, 5):.1f} / 95% {np.percentile(raw, 95):.1f})"
              f"  →  보정 후 50.0 (5% 5.0 / 95% 95.0)\n", flush=True)

    payload = {
        "version": 1,
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": str(src),
        "n_per_field": counts,
        "seed": args.seed,
        "note": "d = p_pos - p_neg 의 분야별 분위수. 서빙은 np.interp(d, quantiles, grid).",
        "grid": grid,
        "quantiles": quantiles,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}  ({out.stat().st_size:,} bytes, {time.time() - started:.0f}s)")
    print("\n워커를 재시작하면 적용됩니다. 끄려면 TONE_CALIBRATION=0.")


if __name__ == "__main__":
    main()
