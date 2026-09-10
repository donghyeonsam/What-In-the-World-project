"""톤 분류 모델 adapter.

외부 계약은 Spark와 동일한 0~100 score를 포함하는 dict다
(spark/apps/article_event.py의 _tone_score가 score만 읽는다).
label/p_pos/p_neg 등은 추가 필드이며 하류를 깨지 않는다.

field_id가 없으면 SOCIETY 가설로 채점한다. 분야를 알수록 정확해진다.
"""

from .tone import score_article


def analyze_sentiment(article, field_id=None, theme_id=None):
    """기사 논조를 채점한다. 반환 dict의 model 필드로 dummy 여부를 구분한다."""
    return score_article(article, field_id=field_id, theme_id=theme_id)
