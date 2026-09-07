"""
NLP 처리 파이프라인 패키지.

언어 감지, 국가 추출, 임베딩 생성,
도메인/테마 분류, 감성 분석 등의 NLP 로직을 관리한다.
"""

from datetime import datetime, timezone

# 임시 함수!!!!!
# 하나의 기사에 NLP 처리 결과를 추가하고 가공된 기사를 반환한다.
def process_article(article):
    article["nlp_worker_data"] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "version": "v1",
    }

    return article