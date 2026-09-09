"""실제 모델 연결 전 고정값 adapter. 50.0은 분석 결과가 아니다."""


def analyze_sentiment(article):
    """외부 계약은 Spark와 동일한 0~100 score만 반환한다."""
    return {"score": 50.0}
