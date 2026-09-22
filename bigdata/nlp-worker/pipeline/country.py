"""
기사 국가 정보 처리 모듈.

1. Collector의 47개 발행 국가를 2글자 국가 코드로 변환한다.
2. 긴 기사는 겹치는 구간으로 나누어 GLiNER로 국가 엔티티를 추출한다.
3. 추출 영역은 Babel/CLDR와 ISO 국가명으로 코드화한다. 언급국은 전 세계 대상이다.
4. GLiNER가 놓칠 수 있는 명확한 국가 표현만 직접 검색해 보완한다.
5. 모델과 직접 검색이 같은 위치에서 찾은 국가는 한 번만 집계한다.
"""

import re
from collections import Counter
from functools import lru_cache

import pycountry
from babel import Locale, UnknownLocaleError


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

# Publishing countries in the collector's global47 profile, using its exact names.
SOURCE_COUNTRY_CODE_MAP = {
    "Argentina": "ar",
    "Australia": "au",
    "Austria": "at",
    "Bangladesh": "bd",
    "Belgium": "be",
    "Brazil": "br",
    "Canada": "ca",
    "Chile": "cl",
    "Colombia": "co",
    "Czech Republic": "cz",
    "Denmark": "dk",
    "Finland": "fi",
    "France": "fr",
    "Germany": "de",
    "Hong Kong": "hk",
    "India": "in",
    "Indonesia": "id",
    "Iran": "ir",
    "Iraq": "iq",
    "Ireland": "ie",
    "Israel": "il",
    "Italy": "it",
    "Japan": "jp",
    "Kazakhstan": "kz",
    "Malaysia": "my",
    "Mexico": "mx",
    "Netherlands": "nl",
    "Pakistan": "pk",
    "Peru": "pe",
    "Philippines": "ph",
    "Poland": "pl",
    "Portugal": "pt",
    "Romania": "ro",
    "Russia": "ru",
    "Saudi Arabia": "sa",
    "Singapore": "sg",
    "South Africa": "za",
    "South Korea": "kr",
    "Spain": "es",
    "Sweden": "se",
    "Switzerland": "ch",
    "Thailand": "th",
    "Turkey": "tr",
    "United Arab Emirates": "ae",
    "United Kingdom": "gb",
    "United States": "us",
    "Vietnam": "vn",
}
SOURCE_COUNTRY_CODES = frozenset(SOURCE_COUNTRY_CODE_MAP.values())


def _country_name_key(name):
    # Keep regex matching compatible with German ß and Turkish dotted İ.
    return " ".join(name.split()).lower().replace("\u0307", "")


def get_country_code(country_name):
    if not isinstance(country_name, str) or not country_name.strip():
        return None

    name = " ".join(country_name.split())
    mapped_code = SOURCE_COUNTRY_CODE_MAP.get(name)
    if mapped_code:
        return mapped_code
    # Also accept ISO codes and alternate names, but only for publishing countries.
    try:
        country_code = pycountry.countries.lookup(name).alpha_2.lower()
    except LookupError:
        # CLDR has common English names such as Russia and Iran, whereas ISO
        # may only expose Russian Federation / Iran, Islamic Republic of.
        country_code = build_country_name_map("en").get(_country_name_key(name))

    return country_code if country_code in SOURCE_COUNTRY_CODES else None


# =========================================================
# Country Aliases
# =========================================================

# 국가명 정규화에도 사용하고,
# 일부 표현은 기사 전체에서 직접 검색하는 데도 사용한다.
COUNTRY_ALIASES = {
    "Turkey": "tr",
    "Türkiye": "tr",
    "Republic of Turkey": "tr",
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

# Only match these case-sensitively inside model-detected entities: "us" is
# also an English pronoun, and bare ISO codes are not safe full-text aliases.
COUNTRY_ABBREVIATIONS = {
    "US": "us", "USA": "us", "U.S.": "us", "U.S.A.": "us",
    "UK": "gb", "U.K.": "gb", "UAE": "ae", "U.A.E.": "ae",
    "ROK": "kr", "DPRK": "kp",
}

# These names can also mean food in English, Spanish or Portuguese.
# They still normalize normally when GLiNER identifies a country entity.
AMBIGUOUS_DIRECT_NAMES = frozenset({"turkey", "chile", "peru"})


@lru_cache(maxsize=64)
def build_country_name_map(language_code):
    """
    GLiNER가 추출한 엔티티를 정규화하기 위한
    국가명 -> ISO alpha-2 코드 맵을 만든다.
    """

    country_map = {}

    # Keep English CLDR names (e.g. Russia) in every language. Accept both
    # fastText codes and BCP-47 tags such as zh-Hant.
    for locale_code in ("en", language_code):
        try:
            locale = Locale.parse((locale_code or "en").replace("-", "_"))
        except (ValueError, UnknownLocaleError):
            continue
        for country in pycountry.countries:
            localized_name = locale.territories.get(country.alpha_2)
            if localized_name:
                country_map[_country_name_key(localized_name)] = country.alpha_2.lower()

    # 영어 공식 국가명
    for country in pycountry.countries:
        code = country.alpha_2.lower()

        country_map[_country_name_key(country.name)] = code

        if hasattr(country, "official_name"):
            country_map[
                _country_name_key(country.official_name)
            ] = code

        if hasattr(country, "common_name"):
            country_map[
                _country_name_key(country.common_name)
            ] = code

    # All 47 collector names must also normalize inside article entities.
    for aliases in (SOURCE_COUNTRY_CODE_MAP, COUNTRY_ALIASES):
        for name, code in aliases.items():
            country_map[_country_name_key(name)] = code

    return country_map


# =========================================================
# GLiNER
# =========================================================

def _iter_country_chunks(text, model):
    """Cover the whole article within both word and transformer token limits."""
    processor = model.data_processor
    tokenizer = processor.transformer_tokenizer
    word_limit = model.config.max_len
    # Cap tokenizers that advertise an effectively infinite context length.
    # The multilingual v2.1 backbone has a 512-token context.
    token_limit = min(512, tokenizer.model_max_length)
    prompt = [model.config.ent_token, "country", model.config.sep_token]
    start = 0
    while start < len(text):
        end = min(start + 1600, len(text))
        while True:
            chunk = text[start:end]
            words = [word for word, _, _ in processor.words_splitter(chunk)]
            if len(words) <= word_limit:
                encoded = tokenizer(
                    prompt + words,
                    is_split_into_words=True,
                    truncation=False,
                    add_special_tokens=True,
                )
                if len(encoded["input_ids"]) <= token_limit:
                    break
            if end - start <= 1:
                raise ValueError("GLiNER context is too small for a country input")
            end = start + (end - start) // 2

        if words:
            yield start, chunk
        if end == len(text):
            break
        # Overlap also covers languages without spaces. Preserve original
        # text so all predictions can be shifted back to article coordinates.
        start = end - min(128, (end - start) // 4)


def extract_country_entities(article):
    title = article.get("title", "") or ""
    body = article.get("body", "") or ""

    text = f"{title}\n{body}".strip()

    if not text:
        return []

    model = get_country_model()
    entities = {}
    for offset, chunk in _iter_country_chunks(text, model):
        for entity in model.predict_entities(chunk, labels=["country"], threshold=0.3):
            start = offset + entity["start"]
            end = offset + entity["end"]
            # A cut through a word must not manufacture a country name.
            if start == offset and start > 0 and text[start - 1:start + 1].isalnum():
                continue
            if end == offset + len(chunk) and end < len(text) and text[end - 1:end + 1].isalnum():
                continue
            key = (start, end)
            if key not in entities or entity.get("score", 0) > entities[key].get("score", 0):
                entities[key] = {**entity, "start": start, "end": end, "text": text[start:end]}
    return [entities[key] for key in sorted(entities)]


# =========================================================
# Entity Normalization
# =========================================================

def _country_pattern(name):
    pattern = r"\s+".join(re.escape(part) for part in name.split())
    if re.search(r"[\u0600-\u06ff]", name):
        # Arabic conjunctions/prepositions attach to names (وفرنسا, باليابان).
        # Look behind the prefix without including it in the country span.
        left = (
            r"(?:(?<!\w)|(?<=[وفبكل])(?<!\w[وفبكل])"
            r"|(?<=[وف][بكل])(?<!\w[وف][بكل]))"
        )
        return left + pattern + r"(?!\w)"
    # CJK particles and Thai text need substring matching; other scripts need
    # Unicode boundaries, including Cyrillic, Arabic and accented Latin.
    if not re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0e00-\u0e7f]", name):
        pattern = r"(?<!\w)" + pattern + r"(?!\w)"
    return pattern


@lru_cache(maxsize=64)
def _entity_country_patterns(language_code):
    return tuple(
        (re.compile(_country_pattern(name), re.IGNORECASE), code)
        for name, code in sorted(
            build_country_name_map(language_code).items(),
            key=lambda item: len(item[0]), reverse=True,
        )
    )


def _deduplicate_mentions(mentions):
    """Prefer the longest country name at each location, including across chunks."""
    result = []
    for code, start, end in sorted(set(mentions), key=lambda m: (-(m[2] - m[1]), m)):
        if not any(start < e and end > s for _, s, e in result):
            result.append((code, start, end))
    return result


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

    mentions = []
    occupied = []

    for pattern, country_code in _entity_country_patterns(language_code):
        for match in pattern.finditer(entity_text):
            relative_start, relative_end = match.span()

            # 긴 국가명 안의 짧은 국가명이 중복 집계되는 것 방지
            overlap = any(
                relative_start < end
                and relative_end > start
                for start, end in occupied
            )

            if overlap:
                continue

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

    for name, code in COUNTRY_ABBREVIATIONS.items():
        for match in re.finditer(_country_pattern(name), entity_text):
            mentions.append((code, entity_start + match.start(), entity_start + match.end()))

    return _deduplicate_mentions(mentions)


# =========================================================
# Safe Fallback Search
# =========================================================

@lru_cache(maxsize=64)
def _safe_direct_patterns(language_code):
    # Restrict automatic dictionary fallback to the 47 publishing countries.
    # Entity normalization itself continues to cover all ISO countries.
    aliases = {
        name: code for name, code in build_country_name_map(language_code).items()
        if code in SOURCE_COUNTRY_CODES and name not in AMBIGUOUS_DIRECT_NAMES
    }
    aliases.update(SAFE_DIRECT_ALIASES)
    return tuple(
        (re.compile(_country_pattern(name), re.IGNORECASE), code)
        for name, code in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)
    )


def find_safe_direct_mentions(text, language_code="en"):
    """
    GLiNER가 놓칠 수 있는 명확한 국가 표현만
    기사 전체에서 직접 검색한다.
    """

    mentions = []

    occupied = []

    for pattern, country_code in _safe_direct_patterns(language_code):
        for match in pattern.finditer(text):
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
        text, language_code
    )

    for mention in direct_mentions:
        mentions.add(mention)

    # 3. 국가별 count 계산
    country_counter = Counter(
        country_code
        for country_code, _, _ in _deduplicate_mentions(mentions)
    )

    return [
        {
            "country_code": country_code,
            "count": count,
        }
        for country_code, count
        in sorted(country_counter.items())
    ]
