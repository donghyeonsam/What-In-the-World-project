"""[stage 0] 정제 — 원본 JSONL(들) → work/clean.jsonl

하는 일
  1. 여러 입력 파일을 읽고 article_id 로 중복 제거
  2. 크롤 실패·빈 제목 제외
  3. 제외 소스 필터 (소스명 + 도메인 양쪽 검사)
  4. 도메인 기준 국가 교정 (theguardian 이 United States 로 온 사례)
  5. 제목 정규화 중복 제거 (통신사 재게재 → train/val 누수 방지)
  6. 본문 품질 게이트 (기사 대신 메뉴·목록·광고벽을 긁어온 경우)
  7. 본문 길이 상한 (목록·색인 페이지가 비용을 독점하는 것 방지)
  8. 상용구 제거, 언어 코드 부여

실행
    python -m distill.prepare
    python -m distill.prepare --limit 5000      # 소규모 점검
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

from .config import load_config, work_path
from .io_utils import read_jsonl, write_jsonl
from .text import clean_text


def resolve_inputs(pattern) -> list[Path]:
    """config.data.input 을 실제 파일 목록으로. 단일 파일 / glob 둘 다 받는다."""
    p = Path(pattern).expanduser()
    if p.exists() and p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.glob("*.jsonl"))
    matches = sorted(Path(p.parent).glob(p.name))
    if not matches:
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {pattern}")
    return matches


def domain_of(url: str) -> str:
    if not url:
        return ""
    s = url.split("//", 1)[-1]
    return s.split("/", 1)[0].lower().removeprefix("www.")


def title_key(title: str) -> str:
    """대소문자·공백 차이를 무시한 제목 키.

    통신사 기사를 여러 매체가 재게재할 때 공백 하나가 달라지는 일이 흔하다.
    문자열 완전일치로만 보면 그 쌍이 train 과 val 에 갈라져 들어가 누수가 된다.
    """
    return hashlib.sha1("".join(title.lower().split()).encode("utf-8")).hexdigest()


def is_excluded(source_name: str, domain: str, patterns: list[str]) -> bool:
    """소스명과 도메인 양쪽에서 찾는다.

    source_name 만 보면 'golem' 같은 도메인 기준 제외가 걸리지 않는다.
    (source_name 이 "Golem.de - IT-News" 가 아니라 다른 표기일 수 있다)
    """
    hay = f"{source_name or ''} {domain or ''}".lower()
    return any(p.lower() in hay for p in patterns)


def body_quality_reason(body: str, q) -> str | None:
    """본문이 기사가 아니면 이유를, 정상이면 None 을 돌려준다.

    두 가지를 본다.
      · 길이      — 너무 짧으면 티저·요약 카드다
      · 문장다움  — 기사에는 40자 넘는 줄이 반드시 있고,
                     메뉴·헤드라인 목록은 짧은 줄만 나열된다
    """
    if not q.enabled:
        return None

    body = body or ""

    min_chars = int(getattr(q, "min_body_chars", 0) or 0)
    if min_chars and len(body) < min_chars:
        return "short_body"

    longest = max((len(l.strip()) for l in body.split("\n")), default=0)
    if longest >= q.min_longest_line:
        return None

    head = body[:400]
    if any(m in head for m in q.teaser_markers):
        return "teaser_only"
    if any(m.lower() in head.lower() for m in q.wall_markers):
        return "paywall_or_adwall"
    return "no_sentence"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="입력 앞에서 N건만 읽는다 (점검용)")
    args = ap.parse_args()

    cfg = load_config()
    out_path = work_path(cfg, "clean.jsonl")
    inputs = resolve_inputs(cfg.data.input)

    exclude = list(cfg.data.exclude_sources)
    if cfg.data.exclude_opinion_sources:
        exclude += list(cfg.data.opinion_sources)

    max_body = getattr(cfg.data, "max_body_chars", 0)
    overrides = getattr(cfg.data, "domain_country_overrides", None) or {}

    stats = collections.Counter()
    corrected: collections.Counter = collections.Counter()
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    kept: list[dict] = []

    print(f"입력 파일 {len(inputs)}개")
    for path in inputs:
        n_before = stats["total"]
        for r in read_jsonl(path):
            if args.limit and stats["total"] >= args.limit:
                break
            stats["total"] += 1

            # 1. 파일 간·파일 내 중복
            aid = r.get("article_id")
            if aid:
                if aid in seen_ids:
                    stats["drop_duplicate_id"] += 1
                    continue
                seen_ids.add(aid)

            # 2. 크롤 실패
            if not r.get("success") or r.get("error"):
                stats["drop_crawl_failed"] += 1
                continue
            title = clean_text(r.get("title"))
            if not title:
                stats["drop_empty_title"] += 1
                continue

            # 3. 제외 소스 — 소스명과 도메인 양쪽
            url = r.get("article_url") or r.get("url") or ""
            domain = domain_of(url)
            if is_excluded(r.get("source_name", ""), domain, exclude):
                stats["drop_excluded_source"] += 1
                continue

            # 4. 도메인 기준 국가 교정
            country = r.get("country")
            if domain in overrides and overrides[domain] != country:
                corrected[f"{domain}: {country} → {overrides[domain]}"] += 1
                country = overrides[domain]

            # 5. 제목 중복 (정규화 후 비교)
            key = title_key(title)
            if key in seen_titles:
                stats["drop_duplicate_title"] += 1
                continue
            seen_titles.add(key)

            # 6. 본문 품질
            body = clean_text(r.get("body"))
            reason = body_quality_reason(body, cfg.data.body_quality)
            if reason:
                stats[f"drop_body_{reason}"] += 1
                continue

            # 7. 본문 길이 상한 — 버리지 않고 자른다
            if max_body and len(body) > max_body:
                body = body[:max_body]
                stats["truncated_long_body"] += 1

            # 원문 본문 — 분야 배정 전용.
            #   worker 는 런타임에 상용구를 제거하지 않고 공백만 합쳐 임베딩한다.
            #   정제본으로 배정하면 worker 의 라우팅과 다른 분야가 나올 수 있다.
            #   (실측: 기사 34%가 정제로 텍스트가 달라지고, 1.7%는 30% 이상 축소)
            #   자르지 않는다 — worker 도 자르지 않는다.
            body_raw = r.get("body") or ""
            if body_raw != body:
                stats["body_cleaned"] += 1

            # 8. 언어
            lang = cfg.data.country_to_lang.get(country)
            if not lang:
                stats["drop_unknown_country"] += 1
                continue

            kept.append({
                "article_id": aid,
                "source_id": r.get("source_id"),
                "source_name": r.get("source_name"),
                "domain": domain,
                "country": country,
                "lang": lang,
                "published_at": r.get("published_at"),
                "url": url,
                "title": title,
                "body": body,            # 정제본 — teacher 라벨링 / student 학습용
                "body_raw": body_raw,    # 원문 — 분야 배정용 (worker 와 동일 입력)
                # worker 가 이미 붙였다면 그대로 들고 간다 (assign_field 가 건너뜀)
                "section": r.get("section"),
                "field_id": r.get("field_id"),
                "theme_id": r.get("theme_id"),
            })
            stats["kept"] += 1
        print(f"  {path.name:<40}{stats['total'] - n_before:>8,}줄")
        if args.limit and stats["total"] >= args.limit:
            break

    write_jsonl(out_path, kept)

    print(f"\n입력  {stats['total']:>8,}건")
    for k in sorted(stats):
        if k.startswith("drop_"):
            print(f"  - {k[5:]:<24}{stats[k]:>8,}")
    if stats["truncated_long_body"]:
        print(f"  (본문 상한 적용 {stats['truncated_long_body']:,}건)")
    if stats["body_cleaned"]:
        print(f"  (상용구 제거로 본문이 바뀐 기사 {stats['body_cleaned']:,}건 "
              f"— 분야 배정에는 원문 body_raw 를 쓴다)")
    print(f"출력  {stats['kept']:>8,}건  ({stats['kept'] / max(stats['total'], 1):.1%})"
          f"  → {out_path}")

    if corrected:
        print("\n도메인 기준 국가 교정:")
        for k, n in corrected.most_common():
            print(f"  {k}  {n:,}건")

    by_lang = collections.Counter(r["lang"] for r in kept)
    print("언어별:", dict(by_lang.most_common()))

    # 소스별 잔존량 — 어느 매체가 통째로 걸러졌는지 여기서 보인다
    by_source = collections.Counter(r["source_name"] for r in kept)
    report = {
        "total": stats["total"],
        "kept": stats["kept"],
        "drops": {k[5:]: v for k, v in stats.items() if k.startswith("drop_")},
        "truncated_long_body": stats["truncated_long_body"],
        "country_corrections": dict(corrected),
        "by_lang": dict(by_lang),
        "by_source_top50": dict(by_source.most_common(50)),
    }
    report_path = work_path(cfg, "prepare_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"리포트 → {report_path}")

    have_field = sum(1 for r in kept if r.get("field_id"))
    if have_field:
        print(f"field_id 보유: {have_field:,}건 — assign_field 를 건너뛸 수 있습니다")
    else:
        print("field_id 없음 — 다음 단계로 `python -m distill.assign_field` 를 실행하세요")


if __name__ == "__main__":
    main()
