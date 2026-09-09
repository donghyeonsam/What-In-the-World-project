"""
기사 국가 정보 처리 모듈.

1. Collector의 발행 국가를 2글자 국가 코드로 변환한다.
2. GLiNER로 기사에서 국가 엔티티를 추출한다.
3. GLiNER가 추출한 영역은 Babel/CLDR로 국가 코드화한다.
4. GLiNER가 놓칠 수 있는 명확한 국가 표현만 직접 검색해 보완한다.
"""

import re
from collections import Counter
from functools import lru_cache

import pycountry
from babel import Locale


# =========================================================
# Model
# =========================================================

MODEL_NAME = "urchade/gliner_multi-v2.1"

_country_model = None


def get_country_model():
    global _country_model
    if _country_model is None:
        from gliner import GLiNER
        _country_model = GLiNER.from_pretrained(MODEL_NAME)
        _country_model.eval()
    return _country_model


# =========================================================
# Source Country
# =========================================================

SOURCE_COUNTRY_CODE_MAP = {
    "South Korea": "kr",
    "United States": "us",
    "Japan": "jp",
    "United Kingdom": "gb",
    "Germany": "de",
}


def get_country_code(country_name):
    if not country_name:
        return None

    return SOURCE_COUNTRY_CODE_MAP.get(country_name.strip())


# =========================================================
# Country Aliases
# =========================================================

# 국가명 정규화에도 사용하고,
# 일부 표현은 기사 전체에서 직접 검색하는 데도 사용한다.
COUNTRY_ALIASES = {
    # Korea
    "South Korea": "kr",
    "Republic of Korea": "kr",
    "대한민국": "kr",
    "한국": "kr",
    "韓国": "kr",

    "North Korea": "kp",
    "북한": "kp",
    "北朝鮮": "kp",

    # United States
    "United States": "us",
    "United States of America": "us",
    "미국": "us",
    "米国": "us",

    # United Kingdom
    "United Kingdom": "gb",
    "Britain": "gb",
    "영국": "gb",
    "英国": "gb",

    # Japan
    "Japan": "jp",
    "일본": "jp",
    "日本": "jp",

    # Germany
    "Germany": "de",
    "독일": "de",
    "ドイツ": "de",
}


# 기사 전체에서 직접 검색해도 비교적 안전한 표현만 둔다.
SAFE_DIRECT_ALIASES = {
    "대한민국": "kr",
    "한국": "kr",
    "韓国": "kr",

    "북한": "kp",
    "北朝鮮": "kp",

    "미국": "us",
    "米国": "us",

    "영국": "gb",
    "英国": "gb",

    "일본": "jp",
    "日本": "jp",

    "독일": "de",
    "ドイツ": "de",

    # 일본어 뉴스에서 자주 등장
    "中国": "cn",

    # 아랍어에서 비교적 명확한 국가명
    "الصين": "cn",
    "اليابان": "jp",
    "الهند": "in",
    "فرنسا": "fr",
    "ألمانيا": "de",
    "الولايات المتحدة": "us",
}


# =========================================================
# Country Name Map
# =========================================================

@lru_cache(maxsize=None)
def build_country_name_map(language_code):
    """
    GLiNER가 추출한 엔티티를 정규화하기 위한
    국가명 -> ISO alpha-2 코드 맵을 만든다.
    """

    country_map = {}

    # 해당 언어의 CLDR 국가명
    try:
        locale = Locale.parse(language_code)

        for country in pycountry.countries:
            localized_name = locale.territories.get(
                country.alpha_2
            )

            if localized_name:
                country_map[
                    localized_name.casefold()
                ] = country.alpha_2.lower()

    except Exception:
        pass

    # 영어 공식 국가명
    for country in pycountry.countries:
        code = country.alpha_2.lower()

        country_map[country.name.casefold()] = code

        if hasattr(country, "official_name"):
            country_map[
                country.official_name.casefold()
            ] = code

        if hasattr(country, "common_name"):
            country_map[
                country.common_name.casefold()
            ] = code

    # 프로젝트 alias
    for name, code in COUNTRY_ALIASES.items():
        country_map[name.casefold()] = code

    return country_map


# =========================================================
# GLiNER
# =========================================================

def extract_country_entities(article):
    title = article.get("title", "") or ""
    body = article.get("body", "") or ""

    text = f"{title}\n{body}".strip()

    if not text:
        return []

    return get_country_model().predict_entities(
        text,
        labels=["country"],
        threshold=0.3,
    )


# =========================================================
# Entity Normalization
# =========================================================

def extract_country_mentions_from_entity(
        entity,
        language_code,
):
    """
    GLiNER가 반환한 하나의 엔티티 안에서
    실제 국가별 위치를 찾아낸다.

    예:
    "미국과 일본"
        -> us, jp

    "日本と韓国"
        -> jp, kr
    """

    entity_text = entity.get("text", "")
    entity_start = entity.get("start", 0)

    if not entity_text:
        return []

    country_map = build_country_name_map(
        language_code
    )

    names = sorted(
        country_map.keys(),
        key=len,
        reverse=True,
    )

    mentions = []
    occupied = []

    for country_name in names:
        if not country_name:
            continue

        pattern = re.escape(country_name)
        # Keep Latin country names at word boundaries; preserve CJK particles.
        if re.search(r"[A-Za-z]", country_name):
            pattern = r"(?<!\w)" + pattern + r"(?!\w)"

        for match in re.finditer(
                pattern,
                entity_text,
                flags=re.IGNORECASE,
        ):
            relative_start, relative_end = match.span()

            # 긴 국가명 안의 짧은 국가명이 중복 집계되는 것 방지
            overlap = any(
                relative_start < end
                and relative_end > start
                for start, end in occupied
            )

            if overlap:
                continue

            country_code = country_map[
                country_name
            ]

            mentions.append(
                (
                    country_code,
                    entity_start + relative_start,
                    entity_start + relative_end,
                )
            )

            occupied.append(
                (relative_start, relative_end)
            )

    return mentions


# =========================================================
# Safe Fallback Search
# =========================================================

def find_safe_direct_mentions(text):
    """
    GLiNER가 놓칠 수 있는 명확한 국가 표현만
    기사 전체에서 직접 검색한다.
    """

    mentions = []

    aliases = sorted(
        SAFE_DIRECT_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    occupied = []

    for alias, country_code in aliases:
        pattern = re.escape(alias)

        for match in re.finditer(
                pattern,
                text,
                flags=re.IGNORECASE,
        ):
            start, end = match.span()

            overlap = any(
                start < used_end
                and end > used_start
                for used_start, used_end in occupied
            )

            if overlap:
                continue

            mentions.append(
                (country_code, start, end)
            )

            occupied.append(
                (start, end)
            )

    return mentions


# =========================================================
# Final
# =========================================================

def extract_mentioned_countries(
        article,
        language_code,
):
    title = article.get("title", "") or ""
    body = article.get("body", "") or ""

    text = f"{title}\n{body}".strip()

    if not text:
        return []

    mentions = set()

    # 1. GLiNER 결과
    entities = extract_country_entities(article)

    for entity in entities:
        entity_mentions = (
            extract_country_mentions_from_entity(
                entity,
                language_code,
            )
        )

        for mention in entity_mentions:
            mentions.add(mention)

    # 2. 신뢰 가능한 alias로 누락 보완
    direct_mentions = find_safe_direct_mentions(
        text
    )

    for mention in direct_mentions:
        mentions.add(mention)

    # 3. 국가별 count 계산
    country_counter = Counter(
        country_code
        for country_code, _, _ in mentions
    )

    return [
        {
            "country_code": country_code,
            "count": count,
        }
        for country_code, count
        in sorted(country_counter.items())
    ]