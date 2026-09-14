"""분야별 톤 가설 — 이 프로젝트의 도메인 지식이 담긴 파일.

teacher(NLI) 에게 던지는 질문지다. 기사를 전제(premise) 로, 아래 문장을
가설(hypothesis) 로 주고 entailment 확률을 받아 P(긍정) / P(부정) 을 만든다.

왜 분야마다 다른가
  같은 표현이 분야에 따라 극성이 반대이기 때문이다.
    "격차가 벌어졌다"   경제 → 부정 / 스포츠 → 그냥 경기 결과
    "역대 최다"         재난 → 부정 / 관광   → 긍정
  분야별로 가설을 달리 쓰면 그 차이가 각 student 모델의 가중치로 들어간다.

왜 극성당 3개인가 (앙상블)
  NLI 는 가설 '문구' 에 예민하다. 하나만 쓰면 그 문구의 버릇이 그대로 라벨이
  되고, student 가 그 버릇을 통째로 학습한다. 증류에서는 student 가 배우는 게
  정답표가 아니라 0.88 이라는 숫자 자체라 특히 치명적이다.
  3개를 평균내면 개별 문구의 편향이 상쇄된다.

작성 원칙
  · 세 문장이 같은 말을 바꿔 쓴 게 아니라 서로 다른 각도여야 한다
    (서술 태도 / 사건의 방향 / 프레이밍)
  · 중립 기사에 상투적으로 걸리는 단어를 피한다
    예) ECONOMY 부정에서 "risk" 를 뺐다 — 평범한 경제 기사도 리스크를
        의례적으로 언급해 부정 가설이 중립 텍스트에 과하게 걸렸다
  · 특정 정파·국가·인물에 유리하거나 불리한 표현을 쓰지 않는다

분야 코드는 NLP worker 의 theme_catalog.json field_id 와 같아야 한다.
    1 POLITICS  2 ECONOMY  3 SOCIETY  4 TECH  5 SPORTS
"""
from __future__ import annotations

# =====================================================================
# 영어 가설 (hypothesis_lang: en)
#
#   다국어 NLI teacher 는 전제가 한국어·일본어·독일어여도 영어 가설로
#   채점할 수 있다. 가설을 한 언어로 고정하면 언어마다 문구가 달라져
#   생기는 편차가 사라진다.
# =====================================================================
TONE_EN: dict[str, tuple[list[str], list[str]]] = {

    # -----------------------------------------------------------------
    # 1. 정치 — 선거, 외교, 국방, 안보, 의회, 정당, 행정, 사법,
    #           국제기구, 이민·난민, 지방정치, 인권
    # -----------------------------------------------------------------
    "POLITICS": (
        [
            "This article describes the political situation in a favorable light.",
            "The article reports agreement, cooperation, or a resolved dispute.",
            "This report frames the political development as a step forward.",
        ],
        [
            "This article describes the political situation in an unfavorable light.",
            "The article reports conflict, breakdown, scandal, or abuse of power.",
            "This report frames the political development as a step backward.",
        ],
    ),

    # -----------------------------------------------------------------
    # 2. 경제 — 금리, 물가, 환율, 증시, 부동산, 고용, 무역, 산업, 금융,
    #           에너지, 기업, 투자, 공급망, 소비
    # -----------------------------------------------------------------
    "ECONOMY": (
        [
            "This article describes the economic situation or outlook optimistically.",
            "The article reports growth, gains, or improving economic indicators.",
            "This report frames the business or market news as good news.",
        ],
        [
            # "risk" 를 뺐다 — 중립적인 경제 기사도 리스크·변동성을 상투적으로
            # 언급해 부정 가설이 중립 텍스트에 과하게 걸렸다.
            "This article describes the economic situation or outlook pessimistically.",
            "The article reports contraction, losses, or worsening economic indicators.",
            "This report frames the business or market news as bad news.",
        ],
    ),

    # -----------------------------------------------------------------
    # 3. 사회 — 범죄·수사, 재난·사고, 교육, 보건·의료, 복지, 노동, 교통,
    #           환경, 인구, 주거, 관광, 문화·종교, 지역사회
    #
    #   주의: 이 분야에 재난·범죄와 문화·관광이 함께 들어 있다.
    #   "역대 최다", "급증" 같은 표현의 극성이 테마에 따라 뒤집히므로,
    #   사건의 방향(피해인가 개선인가)을 묻는 문장으로 구성했다.
    # -----------------------------------------------------------------
    "SOCIETY": (
        [
            "This article reports something that improved people's lives or well-being.",
            "The article describes recovery, relief, achievement, or a community benefiting.",
            "This report frames the event as welcome news for the public.",
        ],
        [
            "This article reports harm, damage, or suffering affecting people.",
            "The article describes an accident, crime, disaster, or worsening conditions.",
            "This report frames the event as troubling news for the public.",
        ],
    ),

    # -----------------------------------------------------------------
    # 4. 기술 — AI, 반도체, 소프트웨어, 플랫폼, 사이버보안, 클라우드,
    #           데이터, 통신, 로봇, 우주, 바이오, 모빌리티, 배터리,
    #           양자기술, 디지털기기
    # -----------------------------------------------------------------
    "TECH": (
        [
            "This article describes the technology development as a success or advance.",
            "The article reports a working product, a breakthrough, or growing adoption.",
            "This report frames the technology news positively.",
        ],
        [
            # ECONOMY 와 같은 이유로 "risk" 계열을 피했다.
            "This article describes the technology development as a failure or setback.",
            "The article reports a defect, outage, security breach, or abandoned project.",
            "This report frames the technology news negatively.",
        ],
    ),

    # -----------------------------------------------------------------
    # 5. 스포츠 — 축구, 야구, 농구, 배구, 테니스, 배드민턴, 탁구, 골프,
    #             모터스포츠, 격투기, 육상, 수영, 피트니스, 기타
    # -----------------------------------------------------------------
    "SPORTS": (
        [
            "This article reports a win, a record, or a strong performance.",
            "The article describes an athlete or team succeeding.",
            "This report frames the sports news as a triumph.",
        ],
        [
            "This article reports a loss, an injury, or a poor performance.",
            "The article describes an athlete or team failing, or a doping or misconduct case.",
            "This report frames the sports news as a disappointment.",
        ],
    ),
}


# =====================================================================
# 한국어 가설 — 검증용 대안.
#
#   hypothesis_lang: ko 로 바꾸면 이쪽을 쓴다. 400건 정도를 두 언어로
#   각각 라벨링해 비교한 뒤 확정하면 된다. 기본은 en.
# =====================================================================
TONE_KO: dict[str, tuple[list[str], list[str]]] = {
    "POLITICS": (
        ["이 기사는 정치 상황을 긍정적으로 서술한다.",
         "이 기사는 합의, 협력, 갈등 해소를 전한다.",
         "이 기사는 해당 정치 사안을 진전으로 다룬다."],
        ["이 기사는 정치 상황을 부정적으로 서술한다.",
         "이 기사는 갈등, 결렬, 비리, 권한 남용을 전한다.",
         "이 기사는 해당 정치 사안을 후퇴로 다룬다."],
    ),
    "ECONOMY": (
        ["이 기사는 경제 상황이나 전망을 낙관적으로 서술한다.",
         "이 기사는 성장, 이익, 지표 개선을 전한다.",
         "이 기사는 해당 경제·기업 소식을 좋은 소식으로 다룬다."],
        ["이 기사는 경제 상황이나 전망을 비관적으로 서술한다.",
         "이 기사는 위축, 손실, 지표 악화를 전한다.",
         "이 기사는 해당 경제·기업 소식을 나쁜 소식으로 다룬다."],
    ),
    "SOCIETY": (
        ["이 기사는 사람들의 삶이나 복지가 나아진 일을 전한다.",
         "이 기사는 회복, 구조, 성취, 지역사회의 혜택을 서술한다.",
         "이 기사는 해당 사건을 반가운 소식으로 다룬다."],
        ["이 기사는 사람들에게 피해나 고통이 생긴 일을 전한다.",
         "이 기사는 사고, 범죄, 재난, 상황 악화를 서술한다.",
         "이 기사는 해당 사건을 우려스러운 소식으로 다룬다."],
    ),
    "TECH": (
        ["이 기사는 해당 기술 개발을 성공이나 진전으로 서술한다.",
         "이 기사는 작동하는 제품, 돌파구, 확산되는 도입을 전한다.",
         "이 기사는 해당 기술 소식을 긍정적으로 다룬다."],
        ["이 기사는 해당 기술 개발을 실패나 차질로 서술한다.",
         "이 기사는 결함, 장애, 보안 침해, 중단된 프로젝트를 전한다.",
         "이 기사는 해당 기술 소식을 부정적으로 다룬다."],
    ),
    "SPORTS": (
        ["이 기사는 승리, 기록, 좋은 경기력을 전한다.",
         "이 기사는 선수나 팀의 성공을 서술한다.",
         "이 기사는 해당 스포츠 소식을 쾌거로 다룬다."],
        ["이 기사는 패배, 부상, 부진한 경기력을 전한다.",
         "이 기사는 선수나 팀의 실패, 도핑·비위 사안을 서술한다.",
         "이 기사는 해당 스포츠 소식을 실망스러운 일로 다룬다."],
    ),
}


def tone_hypotheses(lang: str, field: str) -> tuple[list[str], list[str]]:
    """(긍정 가설 리스트, 부정 가설 리스트) 를 돌려준다.

    lang  : "en" | "ko"   (config.teacher.hypothesis_lang)
    field : "POLITICS" | "ECONOMY" | "SOCIETY" | "TECH" | "SPORTS"
    """
    table = TONE_KO if lang == "ko" else TONE_EN
    if field not in table:
        raise KeyError(
            f"알 수 없는 분야: {field!r}. "
            f"config.yaml 의 fields 와 이 파일이 어긋났습니다. "
            f"사용 가능: {sorted(table)}"
        )
    pos, neg = table[field]
    return list(pos), list(neg)


def check(fields: list[str], lang: str = "en") -> None:
    """config 의 분야 목록과 이 파일이 맞는지 확인. 시작 시 1회 호출."""
    table = TONE_KO if lang == "ko" else TONE_EN
    missing = [f for f in fields if f not in table]
    extra = [f for f in table if f not in fields]
    if missing:
        raise KeyError(f"가설이 없는 분야: {missing}")
    if extra:
        print(f"[경고] config 에 없는 분야가 hypotheses 에 있습니다: {extra}")
    for f in fields:
        pos, neg = table[f]
        if len(pos) != len(neg):
            print(f"[경고] {f}: 긍정 {len(pos)}개 / 부정 {len(neg)}개 — "
                  f"개수가 다르면 축 간 기저율이 어긋날 수 있습니다.")
