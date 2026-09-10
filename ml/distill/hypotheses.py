"""분야별 NLI 가설. 이 프로젝트의 도메인 지식이 담긴 핵심 파일.

NLI는 가설 '문구'에 예민하다. 하나만 쓰면 그 문구의 버릇이 그대로 라벨이 되고,
student가 그 버릇을 통째로 학습한다. 증류에서는 특히 치명적인데
student가 배우는 게 정답표가 아니라 '0.88이라는 숫자 자체'이기 때문이다.

- 분야: 분야당 가설 2개
- 톤: 극성당 가설 3개 (긍정 3 + 부정 3)

ECONOMY·TECH 부정 가설에서 'risk'를 뺐다. 중립적인 경제 기사도 리스크·변동성을
상투적으로 언급해서, 부정 가설이 중립 텍스트에 과하게 걸렸다.
"""
from __future__ import annotations

CATEGORIES = ["POLITICS", "ECONOMY", "SOCIETY", "TECH", "CULTURE", "SPORTS"]

# --- 분야 가설 (분야당 2개) -------------------------------------------------
CATEGORY_HYPOTHESES: dict[str, dict[str, list[str]]] = {
    "en": {
        "POLITICS": [
            "This text is about politics, government, elections or diplomacy.",
            "This text reports on lawmakers, political parties or public policy decisions.",
        ],
        "ECONOMY": [
            "This text is about the economy, business, markets or trade.",
            "This text reports on companies, prices, employment or financial results.",
        ],
        "SOCIETY": [
            "This text is about society, crime, accidents, health, education or welfare.",
            "This text reports on an incident, court case or social issue affecting ordinary people.",
        ],
        "TECH": [
            "This text is about technology, science, IT or research.",
            "This text reports on software, semiconductors, artificial intelligence or scientific findings.",
        ],
        "CULTURE": [
            "This text is about culture, entertainment, art, music, film or celebrities.",
            "This text reports on a cultural work, performance, broadcast or artist.",
        ],
        "SPORTS": [
            "This text is about sports, athletes or competitive matches.",
            "This text reports on a game result, league standing or player transfer.",
        ],
    },
    "ko": {
        "POLITICS": [
            "이 글은 정치, 정부, 선거 또는 외교에 관한 내용이다.",
            "이 글은 국회의원, 정당 또는 정책 결정에 대해 보도한다.",
        ],
        "ECONOMY": [
            "이 글은 경제, 기업, 시장 또는 무역에 관한 내용이다.",
            "이 글은 기업 실적, 물가, 고용 또는 금융에 대해 보도한다.",
        ],
        "SOCIETY": [
            "이 글은 사회, 범죄, 사고, 보건, 교육 또는 복지에 관한 내용이다.",
            "이 글은 사건, 재판 또는 시민 생활과 관련된 사회 문제를 보도한다.",
        ],
        "TECH": [
            "이 글은 기술, 과학, IT 또는 연구에 관한 내용이다.",
            "이 글은 소프트웨어, 반도체, 인공지능 또는 과학적 발견에 대해 보도한다.",
        ],
        "CULTURE": [
            "이 글은 문화, 연예, 예술, 음악, 영화 또는 유명인에 관한 내용이다.",
            "이 글은 문화 작품, 공연, 방송 또는 예술가에 대해 보도한다.",
        ],
        "SPORTS": [
            "이 글은 스포츠, 운동선수 또는 경기에 관한 내용이다.",
            "이 글은 경기 결과, 리그 순위 또는 선수 이적을 보도한다.",
        ],
    },
}

# --- 톤 가설 (극성당 3개) ---------------------------------------------------
# 분야마다 '좋다/나쁘다'의 의미가 다르다. 같은 표현이 분야에 따라 논조가 반대다.
# 예: "격차가 벌어졌다" — 경제에서는 부정, 스포츠에서는 그냥 경기 결과.
TONE_HYPOTHESES: dict[str, dict[str, dict[str, list[str]]]] = {
    "en": {
        "POLITICS": {
            "pos": [
                "This text describes a political development in favorable or approving terms.",
                "This text reports cooperation, agreement or successful governance.",
                "This text presents the political actors or their decisions in a positive light.",
            ],
            "neg": [
                "This text describes a political development in critical or disapproving terms.",
                "This text reports conflict, scandal, corruption or failure of governance.",
                "This text presents the political actors or their decisions in a negative light.",
            ],
        },
        "ECONOMY": {
            "pos": [
                "This text describes an economic development as favorable or improving.",
                "This text reports growth, recovery, profit or rising demand.",
                "This text presents the economic outlook optimistically.",
            ],
            # 'risk' 계열 어휘 제외: 중립 기사도 리스크를 상투적으로 언급한다.
            "neg": [
                "This text describes an economic development as unfavorable or worsening.",
                "This text reports losses, recession, layoffs or falling demand.",
                "This text presents the economic outlook pessimistically.",
            ],
        },
        "SOCIETY": {
            "pos": [
                "This text describes a social development in a hopeful or constructive way.",
                "This text reports rescue, recovery, relief or an improvement in people's lives.",
                "This text presents the situation as resolved or improving.",
            ],
            "neg": [
                "This text describes a social development in a distressing or alarming way.",
                "This text reports a crime, accident, death, illness or worsening hardship.",
                "This text presents the situation as harmful or deteriorating.",
            ],
        },
        "TECH": {
            "pos": [
                "This text describes a technological development as promising or beneficial.",
                "This text reports a breakthrough, successful launch or improved performance.",
                "This text presents the technology or its makers favorably.",
            ],
            # 'risk' 계열 어휘 제외 (ECONOMY와 같은 이유).
            "neg": [
                "This text describes a technological development as troubled or harmful.",
                "This text reports a failure, defect, breach, outage or abandoned project.",
                "This text presents the technology or its makers unfavorably.",
            ],
        },
        "CULTURE": {
            "pos": [
                "This text describes a cultural work or figure approvingly.",
                "This text reports acclaim, an award, popularity or a successful release.",
                "This text presents the artist or work in a flattering light.",
            ],
            "neg": [
                "This text describes a cultural work or figure disapprovingly.",
                "This text reports criticism, controversy, poor reception or a cancellation.",
                "This text presents the artist or work in an unflattering light.",
            ],
        },
        "SPORTS": {
            "pos": [
                "This text describes a sporting outcome favorably for the subject of the article.",
                "This text reports a victory, record, strong performance or return from injury.",
                "This text presents the athlete or team in a positive light.",
            ],
            "neg": [
                "This text describes a sporting outcome unfavorably for the subject of the article.",
                "This text reports a defeat, injury, poor performance, suspension or dispute.",
                "This text presents the athlete or team in a negative light.",
            ],
        },
    },
    "ko": {
        "POLITICS": {
            "pos": [
                "이 글은 정치적 상황을 긍정적이거나 우호적으로 서술한다.",
                "이 글은 협력, 합의 또는 성공적인 국정 운영을 보도한다.",
                "이 글은 정치 주체나 그 결정을 좋게 평가한다.",
            ],
            "neg": [
                "이 글은 정치적 상황을 비판적이거나 부정적으로 서술한다.",
                "이 글은 갈등, 의혹, 부패 또는 국정 실패를 보도한다.",
                "이 글은 정치 주체나 그 결정을 나쁘게 평가한다.",
            ],
        },
        "ECONOMY": {
            "pos": [
                "이 글은 경제 상황을 좋아지는 것으로 서술한다.",
                "이 글은 성장, 회복, 이익 또는 수요 증가를 보도한다.",
                "이 글은 경제 전망을 낙관적으로 제시한다.",
            ],
            "neg": [
                "이 글은 경제 상황을 나빠지는 것으로 서술한다.",
                "이 글은 손실, 침체, 감원 또는 수요 감소를 보도한다.",
                "이 글은 경제 전망을 비관적으로 제시한다.",
            ],
        },
        "SOCIETY": {
            "pos": [
                "이 글은 사회적 상황을 희망적이거나 건설적으로 서술한다.",
                "이 글은 구조, 회복, 지원 또는 생활 여건 개선을 보도한다.",
                "이 글은 상황이 해결되거나 나아지고 있다고 제시한다.",
            ],
            "neg": [
                "이 글은 사회적 상황을 우려스럽거나 심각하게 서술한다.",
                "이 글은 범죄, 사고, 사망, 질병 또는 악화되는 어려움을 보도한다.",
                "이 글은 상황이 해롭거나 나빠지고 있다고 제시한다.",
            ],
        },
        "TECH": {
            "pos": [
                "이 글은 기술 개발을 유망하거나 이로운 것으로 서술한다.",
                "이 글은 성과, 성공적인 출시 또는 성능 향상을 보도한다.",
                "이 글은 그 기술이나 개발 주체를 좋게 평가한다.",
            ],
            "neg": [
                "이 글은 기술 개발을 문제가 있거나 해로운 것으로 서술한다.",
                "이 글은 실패, 결함, 유출, 장애 또는 개발 중단을 보도한다.",
                "이 글은 그 기술이나 개발 주체를 나쁘게 평가한다.",
            ],
        },
        "CULTURE": {
            "pos": [
                "이 글은 문화 작품이나 인물을 호의적으로 서술한다.",
                "이 글은 호평, 수상, 인기 또는 성공적인 발표를 보도한다.",
                "이 글은 예술가나 작품을 좋게 평가한다.",
            ],
            "neg": [
                "이 글은 문화 작품이나 인물을 부정적으로 서술한다.",
                "이 글은 비판, 논란, 저조한 반응 또는 취소를 보도한다.",
                "이 글은 예술가나 작품을 나쁘게 평가한다.",
            ],
        },
        "SPORTS": {
            "pos": [
                "이 글은 경기 결과를 기사의 주인공에게 유리하게 서술한다.",
                "이 글은 승리, 기록, 좋은 활약 또는 부상 복귀를 보도한다.",
                "이 글은 선수나 팀을 긍정적으로 평가한다.",
            ],
            "neg": [
                "이 글은 경기 결과를 기사의 주인공에게 불리하게 서술한다.",
                "이 글은 패배, 부상, 부진, 징계 또는 분쟁을 보도한다.",
                "이 글은 선수나 팀을 부정적으로 평가한다.",
            ],
        },
    },
}


def category_hypotheses(lang: str = "en") -> dict[str, list[str]]:
    """분야 → 가설 2개."""
    try:
        return CATEGORY_HYPOTHESES[lang]
    except KeyError:
        raise ValueError(
            f"지원하지 않는 hypothesis_lang: {lang} "
            f"(가능: {sorted(CATEGORY_HYPOTHESES)})") from None


def tone_hypotheses(category: str, lang: str = "en") -> dict[str, list[str]]:
    """분야 → {'pos': [3개], 'neg': [3개]}."""
    if lang not in TONE_HYPOTHESES:
        raise ValueError(f"지원하지 않는 hypothesis_lang: {lang}")
    if category not in TONE_HYPOTHESES[lang]:
        raise ValueError(f"알 수 없는 분야: {category}")
    return TONE_HYPOTHESES[lang][category]


def flat_category_pairs(lang: str = "en") -> list[tuple[str, str]]:
    """[(분야, 가설), ...] 순서 고정. 채점 쪽에서 reshape로 되돌린다."""
    h = category_hypotheses(lang)
    return [(c, hyp) for c in CATEGORIES for hyp in h[c]]


def flat_tone_hypotheses(category: str, lang: str = "en") -> tuple[list[str], int]:
    """(긍정 3개 + 부정 3개, 극성당 개수). 순서: pos 먼저."""
    h = tone_hypotheses(category, lang)
    pos, neg = h["pos"], h["neg"]
    if len(pos) != len(neg):
        raise ValueError(f"{category}: 긍정·부정 가설 수가 다름 ({len(pos)} vs {len(neg)})")
    return pos + neg, len(pos)


def self_check() -> None:
    """구조 검증. import 시점에 돈다."""
    for lang, table in CATEGORY_HYPOTHESES.items():
        assert set(table) == set(CATEGORIES), f"{lang}: 분야 누락"
        for c, hyps in table.items():
            assert len(hyps) == 2, f"{lang}/{c}: 분야 가설은 2개여야 함"
    for lang, table in TONE_HYPOTHESES.items():
        assert set(table) == set(CATEGORIES), f"{lang}: 톤 분야 누락"
        for c, pol in table.items():
            assert set(pol) == {"pos", "neg"}, f"{lang}/{c}: 극성 키 오류"
            assert len(pol["pos"]) == len(pol["neg"]) == 3, f"{lang}/{c}: 극성당 3개"
    for lang in ("en", "ko"):
        for c in ("ECONOMY", "TECH"):
            joined = " ".join(TONE_HYPOTHESES[lang][c]["neg"]).lower()
            assert "risk" not in joined and "리스크" not in joined, \
                f"{lang}/{c} 부정 가설에 risk 계열이 다시 들어옴"


self_check()
