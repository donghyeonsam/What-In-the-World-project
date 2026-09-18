"""GMS OpenAI-compatible client for generating issue metadata."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from issue_clustering import ClusterCandidate, GeneratedIssue


class GmsIssueGenerationError(RuntimeError):
    """Raised when GMS does not return a valid issue decision."""


VAGUE_ISSUE_NAME_PATTERNS = (
    re.compile(r"(?:관련\s*)?(?:이슈|뉴스)$"),
)


@dataclass(frozen=True)
class GmsConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 30.0
    max_attempts: int = 3


def _completion_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GmsIssueGenerationError("GMS content must be a JSON object") from exc
    if not isinstance(value, dict):
        raise GmsIssueGenerationError("GMS content must be a JSON object")
    return value


def validate_generated_issue(value: dict[str, Any]) -> GeneratedIssue:
    required_fields = {"name", "summary"}
    if set(value) != required_fields:
        raise GmsIssueGenerationError(
            "GMS content must contain exactly name and summary"
        )
    name = value.get("name")
    summary = value.get("summary")

    if not isinstance(name, str) or not 8 <= len(name.strip()) <= 50:
        raise GmsIssueGenerationError("name must contain 8 to 50 characters")
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 300:
        raise GmsIssueGenerationError("summary must contain 1 to 300 characters")

    normalized_name = " ".join(name.split())
    if "기타" in normalized_name or any(
        pattern.search(normalized_name) for pattern in VAGUE_ISSUE_NAME_PATTERNS
    ):
        raise GmsIssueGenerationError("name is too vague to identify a concrete issue")

    return GeneratedIssue(
        name=normalized_name,
        summary=summary.strip(),
    )


def _request_body(
    config: GmsConfig,
    theme_name: str,
    cluster: ClusterCandidate,
) -> bytes:
    input_value = {
        "theme": theme_name,
        "cluster": {
            "article_count": len(cluster.articles),
            "hdbscan_membership_confidence": cluster.membership_confidence,
            "representative_articles": [
                {
                    "title": article.title,
                    "summary": article.summary,
                }
                for article in cluster.representatives
            ],
        },
    }
    system_prompt = (
        "당신은 여러 국가의 뉴스 기사를 동일한 구체적 사건·결정·주장 단위로 "
        "정규화하는 편집자다. 기사 근거에 없는 사실을 추측하지 마라. 분야명이나 "
        "포괄적 주제를 이슈로 만들지 마라. '관련 이슈', '최근 뉴스'처럼 대상 사건을 "
        "식별할 수 없는 이름을 사용하지 마라. 응답은 name과 summary 필드만 가진 "
        "JSON 객체로 반환한다."
    )
    user_prompt = (
        "다음 대표 기사들이 공통으로 보도하는 가장 구체적인 사건·결정·주장 하나의 "
        "메타데이터를 생성하라. name은 8~50자의 한국어 명사구이며 구체적인 인물·기관·"
        "기업·팀·장소 등 주체, 구체적인 정책·사건·대상, 발생·발표·협상·판결·승패 등 "
        "행동이나 결과가 드러나야 한다. summary는 "
        "대표 기사에서 공통으로 확인되는 사실만 300자 이하로 작성한다. 서로 다른 "
        "사건이 섞여 있더라도 억지로 포괄하는 상위 주제명을 만들지 말고, 가장 많은 "
        "대표 기사가 함께 지지하는 단일 사건을 선택한다.\n"
        + json.dumps(input_value, ensure_ascii=False, separators=(",", ":"))
    )
    return json.dumps(
        {
            "model": config.model,
            "temperature": 0.1,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def generate_issue(
    config: GmsConfig,
    theme_name: str,
    cluster: ClusterCandidate,
) -> GeneratedIssue:
    if not config.api_key.strip():
        raise GmsIssueGenerationError("GMS_API_KEY is required")
    if not config.base_url.strip():
        raise GmsIssueGenerationError("GMS_BASE_URL is required")
    if not config.model.strip():
        raise GmsIssueGenerationError("GMS_MODEL is required")
    if config.max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    last_error: Exception | None = None
    for attempt in range(1, config.max_attempts + 1):
        request = Request(
            _completion_url(config.base_url),
            data=_request_body(config, theme_name, cluster),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                response_value = json.loads(response.read().decode("utf-8"))
            content = response_value["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise GmsIssueGenerationError("GMS response content must be text")
            return validate_generated_issue(_extract_json_object(content))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            KeyError,
            IndexError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            GmsIssueGenerationError,
        ) as exc:
            last_error = exc
            if attempt < config.max_attempts:
                time.sleep(min(2 ** (attempt - 1), 4))

    raise GmsIssueGenerationError(
        f"GMS issue generation failed after {config.max_attempts} attempts: {last_error}"
    ) from last_error
