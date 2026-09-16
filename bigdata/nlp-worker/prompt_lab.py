"""프롬프트 튜닝용 단독 스크립트 — 파이프라인 밖에서 돌린다.

왜 필요한가
  요약 기능에서 시간을 제일 먹는 건 코드가 아니라 "출력을 보고 프롬프트를 고치는
  왕복"이다. 파이프라인 안에서 고치면 한 번 바꿀 때마다 워커를 재시작해야 하고,
  Kafka 에 실제 기사가 흘러야 결과를 볼 수 있다.

  이 스크립트는 아카이브 파일에서 기사를 직접 읽어 vLLM 에만 요청한다.
  Kafka 도 워커도 DB 도 건드리지 않는다. 프롬프트를 고치고 바로 다시 돌리면 된다.

실행
    cd ~/nlp-worker
    source .venv/bin/activate
    python prompt_lab.py --n 20

    # 언어를 골라서
    python prompt_lab.py --n 10 --lang de

    # 제목 번역만
    python prompt_lab.py --n 10 --task title

    # 결과를 파일로 (팀원에게 보여줄 때)
    python prompt_lab.py --n 30 --out lab.md
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import news_prompt, title_translation   # noqa: E402
from pipeline.llm_client import (LLM_BASE_URL, LLM_MODEL, LlmError,  # noqa: E402
                                 chat, verify_server)
from pipeline.summarize import clean, korean_ratio     # noqa: E402

ARCHIVE_GLOB = str(Path.home() / "nlp-worker" / "data" / "raw" / "*.jsonl")
COUNTRY_TO_LANG = {
    "Japan": "ja", "South Korea": "ko", "United States": "en",
    "United Kingdom": "en", "Germany": "de",
}


def load_articles(pattern: str, n: int, lang: str | None, seed: int,
                  min_body: int) -> list[dict]:
    files = sorted(glob.glob(os.path.expanduser(pattern)))
    if not files:
        sys.exit(f"아카이브를 찾지 못했습니다: {pattern}")

    rows = []
    # 최신 파일부터, 각 파일에서 앞쪽 일부만 읽는다 (전체를 읽으면 느리다)
    for path in reversed(files):
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 4000:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                body = (r.get("body") or "").strip()
                if len(body) < min_body:
                    continue
                r["_lang"] = COUNTRY_TO_LANG.get((r.get("country") or "").strip(), "en")
                if lang and r["_lang"] != lang:
                    continue
                rows.append(r)
        if len(rows) >= n * 20:
            break

    if not rows:
        sys.exit("조건에 맞는 기사가 없습니다. --lang 이나 --min-body 를 조정하세요.")
    random.Random(seed).shuffle(rows)
    return rows[:n]


def run_one(article: dict, task: str, body_chars_override: int = 0) -> dict:
    lang = article["_lang"]
    title = (article.get("title") or "").strip()
    body = (article.get("body") or "").strip()

    # 두 작업은 프롬프트가 서로 다르다. 각자 '서비스에서 쓰는 그 함수'를 부른다.
    if task == "title":
        body_chars = body_chars_override or title_translation.BODY_LEAD_MAX_CHARS
        system = None
        user = title_translation._build_prompt(
            title=title, body_lead=body[:body_chars], language_code=lang)
        max_tokens = title_translation.MAX_NEW_TOKENS
    else:
        body_chars = body_chars_override or news_prompt.SUMMARY_BODY_CHARS
        instruction = (news_prompt.TASK_SUMMARY_KO if lang == "ko"
                       else news_prompt.TASK_SUMMARY_TRANSLATE)
        system = news_prompt.SYSTEM
        user = news_prompt.build_user(title, body, lang, instruction,
                                      body_chars=body_chars)
        max_tokens = 300

    t0 = time.time()
    try:
        raw = chat(system, user, max_tokens=max_tokens, temperature=0.0)
        err = None
    except LlmError as exc:
        raw, err = "", str(exc)
    dt = time.time() - t0

    # 후처리도 서비스와 같은 것을 쓴다
    text = (title_translation._clean_translation(raw) if task == "title"
            else clean(raw))
    return {
        "lang": lang,
        "title": title,
        "body_chars": len(body),
        "sent_chars": min(len(body), body_chars),
        "out": text,
        "chars": len(text),
        "korean": korean_ratio(text),
        "sentences": text.count("다.") or text.count("."),
        "sec": dt,
        "error": err,
    }


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="기사 수")
    ap.add_argument("--task", choices=["summary", "title"], default="summary")
    ap.add_argument("--lang", choices=["ko", "en", "de", "ja"], default=None)
    ap.add_argument("--archive", default=ARCHIVE_GLOB)
    ap.add_argument("--min-body", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--body-chars", type=int, default=0,
                    help="본문 상한을 임시로 덮어쓴다 (0이면 각 모듈의 기본값)")
    ap.add_argument("--out", default=None, help="결과를 마크다운으로 저장")
    args = ap.parse_args()

    ok, detail = verify_server()
    if not ok:
        print(f"[경고] {detail}")
        print(f"       {LLM_BASE_URL} 에 우리 vLLM 이 있는지 확인하세요.\n")
    else:
        print(f"서버 확인 {detail}")

    print(f"작업 {args.task}")
    articles = load_articles(args.archive, args.n, args.lang, args.seed, args.min_body)
    print(f"기사 {len(articles)}건\n")

    results = []
    for i, art in enumerate(articles, 1):
        r = run_one(art, args.task, args.body_chars)
        results.append(r)

        flag = ""
        if r["error"]:
            flag = "  ← 호출 실패"
        elif not r["out"]:
            flag = "  ← 빈 출력"
        elif r["korean"] < 0.3:
            flag = f"  ← 한글 {r['korean']:.0%}"
        elif args.task == "summary" and r["chars"] > 400:
            flag = f"  ← {r['chars']}자"

        print(f"[{i:>2}] {r['lang']}  본문 {r['body_chars']:,}자"
              f"(전송 {r['sent_chars']:,})  {r['sec']:.1f}초{flag}")
        print(f"     원제 {r['title'][:70]}")
        print(f"     출력 {r['out'][:200] or r['error']}")
        print()

    ok = [r for r in results if r["out"] and not r["error"]]
    print("=" * 70)
    print(f"  성공        {len(ok)}/{len(results)}")
    if ok:
        chars = sorted(r["chars"] for r in ok)
        secs = sorted(r["sec"] for r in ok)
        print(f"  출력 길이   중앙 {chars[len(chars)//2]}자  "
              f"최소 {chars[0]}  최대 {chars[-1]}")
        print(f"  소요        중앙 {secs[len(secs)//2]:.1f}초  최대 {secs[-1]:.1f}초")
        print(f"  한글 비율   최소 {min(r['korean'] for r in ok):.0%}")
        long_ = [r for r in ok if r["chars"] > 400]
        if long_:
            print(f"  [주의] 400자 초과 {len(long_)}건 — 문장 수 제한이 안 먹고 있습니다")
        notko = [r for r in ok if r["korean"] < 0.3]
        if notko:
            print(f"  [주의] 한글 30% 미만 {len(notko)}건 — 원문 언어로 답하고 있습니다")

    if args.out:
        lines = [f"# 프롬프트 실험 ({args.task})", "",
                 f"- 모델: `{LLM_MODEL}`", f"- 기사: {len(results)}건", ""]
        for i, r in enumerate(results, 1):
            lines += [f"## {i}. [{r['lang']}] {r['title']}", "",
                      f"> {r['out'] or r['error']}", "",
                      f"`{r['chars']}자 / 한글 {r['korean']:.0%} / {r['sec']:.1f}초`", ""]
        Path(args.out).write_text("\n".join(lines), encoding="utf-8")
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
