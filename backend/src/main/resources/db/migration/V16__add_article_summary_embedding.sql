-- 기사 요약문(본문 3문장 한국어 요약)의 E5 임베딩을 저장한다.
--
-- 768차원 float 배열을 JSON 문자열로 보관한다.
-- theme.embedding / issue.embedding 과 동일한 TEXT 방식이며,
-- 직렬화는 DbWriterService.writeJson 이 담당한다.
--
-- NULL 을 허용하는 이유:
--   1. 요약(LLM)이 실패한 기사는 요약도 임베딩도 없다.
--      요약 하나 때문에 기사 전체를 버리지 않는다는 파이프라인 정책과 같다.
--   2. 이 마이그레이션 이전에 저장된 기사는 값이 없다. 백필은 별도로 한다.
ALTER TABLE article
    ADD COLUMN summary_embedding TEXT NULL;
