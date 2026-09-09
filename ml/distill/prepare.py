"""[0] 정제. 포털·중복·비기사 제거.

python -m distill.prepare [--limit N]

입력: data/news.raw.jsonl (news.raw.v1 이벤트 16필드)
출력: work/clean.jsonl + work/prepare_report.json

원본 필드는 건드리지 않고 필요한 것만 추출해 정규화한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

from .config import input_path, load_config, work_path
from .io_utils import read_jsonl, write_jsonl
from .text import clean_text, longest_line, title_term_overlap


def _domain(url: str) -> str:
    if not url:
        return ""
    s = url.split("//", 1)[-1]
    return s.split("/", 1)[0].lower().removeprefix("www.")


def _pick(row: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return default


def _title_hash(title: str) -> str:
    norm = "".join(title.lower().split())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def is_excluded_source(source: str, domain: str, patterns: list[str]) -> bool:
    hay = f"{source} {domain}".lower()
    return any(p.lower() in hay for p in patterns)


def body_quality_reason(title: str, body: str, bq: dict) -> str | None:
    """탈락 이유 문자열, 통과면 None."""
    if not bq.get("enabled", True):
        return None
    if len(body) < bq.get("min_body_chars", 300):
        return "short_body"
    if longest_line(body) < bq.get("min_longest_line", 40):
        return "headline_list"          # excite류 포털: 본문이 사이드바 목록
    low = body.lower()
    for m in bq.get("wall_markers", []):
        if m.lower() in low:
            return "wall_page"          # golem류 쿠키 동의 화면
    for m in bq.get("teaser_markers", []):
        if m.lower() in low and len(body) < 1200:
            return "teaser"
    # 제목-본문 일치도는 기본적으로 '진단만' 한다.
    # 2차 감사 기준 정상 61.7% / excite 15.7% 로 분리는 되지만,
    # 일본어·독일어 복합어는 부분일치가 잘 깨져서 정상 기사도 0.0이 나온다.
    # 포털 판별은 headline_list / wall_page 가 이미 잡는다.
    thr = float(bq.get("min_title_term_overlap", 0.0) or 0.0)
    if thr > 0 and title and title_term_overlap(title, body) < thr:
        return "title_body_mismatch"
    return None


def normalize(row: dict, cfg) -> dict:
    url = _pick(row, "url", "link")
    dom = _domain(url)
    country = _pick(row, "country")
    country = cfg.data.get("domain_country_overrides", {}).get(dom, country)
    lang = _pick(row, "lang", "language") or \
        cfg.data["country_to_lang"].get(country, "")
    title = clean_text(_pick(row, "title", "headline"), drop_boilerplate=False)
    body = clean_text(_pick(row, "body", "content", "text"))
    return {
        "id": _pick(row, "id", "article_id", "guid") or _title_hash(url or title),
        "url": url,
        "domain": dom,
        "source": _pick(row, "source", "source_name", default=dom),
        "country": country,
        "lang": lang,
        "title": title,
        "body": body,
        "published_at": row.get("published_at"),
        "discovered_at": row.get("discovered_at") or row.get("collected_at"),
        "section": row.get("section"),
    }


def diagnose(rows: list[dict]) -> dict:
    """게이트로 쓰지 않는 진단값. 포털 의심 소스를 소스별로 본다."""
    from collections import defaultdict
    per: dict = defaultdict(list)
    for r in rows:
        per[r["source"]].append(title_term_overlap(r["title"], r["body"]))
    ov = {s: round(sum(v) / len(v), 3) for s, v in per.items() if len(v) >= 10}
    return {"title_term_overlap_by_source": dict(sorted(ov.items(), key=lambda kv: kv[1])[:15])}


def run(cfg, limit: int | None = None) -> dict:
    src = input_path(cfg)
    if not src.exists():
        raise FileNotFoundError(
            f"입력 파일이 없음: {src}\n"
            "크롤 JSONL을 data/news.raw.jsonl 로 두거나 config.yaml의 data.input을 수정")

    bq = dict(cfg.data.get("body_quality", {}))
    excl = list(cfg.data.get("exclude_sources", []))
    if cfg.data.get("exclude_opinion_sources"):
        excl += list(cfg.data.get("opinion_sources", []))
    langs = set(cfg.data["country_to_lang"].values())

    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    drops: Counter = Counter()
    by_lang: Counter = Counter()
    by_source: Counter = Counter()
    kept: list[dict] = []
    total = 0

    for raw in read_jsonl(src, limit=limit):
        total += 1
        r = normalize(raw, cfg)

        if not r["url"] or r["url"] in seen_urls:
            drops["dup_url"] += 1
            continue
        if is_excluded_source(r["source"], r["domain"], excl):
            drops["excluded_source"] += 1
            continue
        if not r["title"] or not r["body"]:
            drops["empty"] += 1
            continue
        if r["lang"] not in langs:
            drops["unknown_lang"] += 1
            continue
        th = _title_hash(r["title"])
        if th in seen_titles:
            drops["dup_title"] += 1
            continue
        reason = body_quality_reason(r["title"], r["body"], bq)
        if reason:
            drops[reason] += 1
            continue

        seen_urls.add(r["url"])
        seen_titles.add(th)
        by_lang[r["lang"]] += 1
        by_source[r["source"]] += 1
        kept.append(r)

    out = work_path(cfg, "clean.jsonl")
    write_jsonl(out, kept)

    report = {
        "input": str(src),
        "output": str(out),
        "total_in": total,
        "kept": len(kept),
        "kept_ratio": round(len(kept) / total, 4) if total else 0.0,
        "drops": dict(drops.most_common()),
        "by_lang": dict(by_lang.most_common()),
        "top_sources": dict(by_source.most_common(20)),
        **diagnose(kept),
    }
    rp = work_path(cfg, "prepare_report.json")
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[prepare] {total} → {len(kept)} ({report['kept_ratio']:.1%})")
    for k, v in report["drops"].items():
        print(f"  drop {k:22s} {v:>7,}")
    print(f"  by_lang: {report['by_lang']}")
    low = report["title_term_overlap_by_source"]
    if low:
        worst = list(low.items())[:5]
        print("  제목-본문 일치도 하위 소스 (정상 ~0.62, 포털 의심 <0.25):")
        for s_, v in worst:
            print(f"    {s_:24s} {v:.3f}")
    print(f"  → {out}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="[0] 정제")
    ap.add_argument("--config", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(load_config(a.config), limit=a.limit)


if __name__ == "__main__":
    main()
