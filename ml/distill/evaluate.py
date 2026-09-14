"""[stage 5] 종합 평가 리포트 — work/report.md

학습이 끝난 모델들을 모아 한 장으로 정리한다.
  · 분야 배정: worker 분류기 재사용 (여기서 학습하는 모델이 아니다)
  · 톤 student 5개: 언어별 MAE · 라벨 일치율 · 라벨 분포
  · 경고: 조합당 표본이 적어 신뢰하기 어려운 셀

실행
    python -m distill.evaluate
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import load_config


def _field_names(cfg) -> list[str]:
    f = cfg.fields
    if isinstance(f, dict):
        return [f[k] for k in sorted(int(x) for x in f)]
    return list(f)


def main() -> None:
    cfg = load_config()
    models_dir = cfg.data.work_dir / "models"
    lines = ["# 증류 결과 리포트", ""]

    # ---- 분야 배정 ----------------------------------------------------
    # 분야 분류기는 학습하지 않는다. NLP worker 의 테마 분류기(68테마 → field_id)
    # 결과를 그대로 쓴다. 학습 때 나눈 기준과 런타임 라우팅 기준이 같아야
    # "자기 같은 기사를 본 적 없는 모델" 에게 채점받는 기사가 생기지 않는다.
    lines += ["## 분야 배정", "",
              "학습하지 않음 — NLP worker 의 테마 분류기를 그대로 사용한다.", ""]
    centroid_p = cfg.data.work_dir / "centroid.npy"
    lines += [f"- 카탈로그: `{cfg.assign.catalog}`",
              f"- 임베딩: worker `pipeline/embedding.py` 직접 호출",
              f"- centroid: `{centroid_p}` "
              f"({'있음' if centroid_p.exists() else '**없음 — 중심화 안 됨**'})", ""]
    if not centroid_p.exists():
        lines += ["> centroid 없이 배정하면 1위-2위 마진이 0.005 수준이라 "
                  "분야가 거의 무작위로 갈린다. `python -m distill.build_centroid` 확인.", ""]

    # ---- 톤 student ---------------------------------------------------
    lines += ["## 톤 student (분야별)", ""]
    langs_all = set()
    rows = []
    for d in cfg.fields:
        meta_p = models_dir / "tone" / d / "meta.json"
        if not meta_p.exists():
            rows.append((d, None)); continue
        m = json.loads(meta_p.read_text())
        rows.append((d, m))
        langs_all |= set(m.get("val_per_lang", {}).keys())
    langs = sorted(langs_all)

    lines += ["### 라벨 일치율 (teacher vs student, val)", ""]
    lines += ["| 분야 | " + " | ".join(langs) + " |",
              "|---|" + "---|" * len(langs)]
    for d, m in rows:
        if m is None:
            lines.append(f"| {d} | " + " | ".join("—" for _ in langs) + " |"); continue
        cells = []
        for l in langs:
            v = m["val_per_lang"].get(l)
            cells.append(f"{v['label_agree']:.3f} (n={v['n']})" if v else "—")
        lines.append(f"| {d} | " + " | ".join(cells) + " |")
    lines.append("")

    lines += ["### MAE (확률 오차, 낮을수록 좋음)", ""]
    lines += ["| 분야 | " + " | ".join(langs) + " |",
              "|---|" + "---|" * len(langs)]
    for d, m in rows:
        if m is None:
            lines.append(f"| {d} | " + " | ".join("—" for _ in langs) + " |"); continue
        cells = []
        for l in langs:
            v = m["val_per_lang"].get(l)
            cells.append(f"{v['mae']:.3f}" if v else "—")
        lines.append(f"| {d} | " + " | ".join(cells) + " |")
    lines.append("")

    # ---- 경고 -----------------------------------------------------------
    warn = []
    for d, m in rows:
        if m is None: continue
        for l, v in m["val_per_lang"].items():
            if v["n"] < cfg.split.min_per_cell // 3:
                warn.append(f"- {d} × {l}: val {v['n']}건 — 표본이 적어 수치를 신뢰하기 어려움")
            elif v["label_agree"] < 0.7:
                warn.append(f"- {d} × {l}: 라벨 일치율 {v['label_agree']:.3f} — 이 조합은 재검토 필요")
    lines += ["## 경고", ""] + (warn or ["없음"]) + [""]

    lines += ["## 산출물", "",
              f"- 톤 student: `{models_dir / 'tone' / '{FIELD}'}` "
              f"(encoder/ · head.pt · meta.json) — 분야별 5개", "",
              "NLP worker 에 넣을 때:", "",
              "1. `tone/` 디렉터리 전체 → worker `models/tone-student/`",
              "2. worker `pipeline/tone.py` 의 `ToneScorer._chunk_probs` 를 "
              "student 추론으로 교체 (외부 계약 `score_article` 은 그대로)",
              "3. `meta.json` 의 pooling·head/tail 절단 설정을 읽어 학습과 같은 방식으로 추론",
              "4. `work/centroid.npy` 를 worker `resources/centroid.npy` 와 "
              "**같은 파일로 유지** — 다르면 학습 때 나눈 분야와 런타임 라우팅이 어긋난다", ""]

    out = cfg.data.work_dir / "report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
