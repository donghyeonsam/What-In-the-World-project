-- 저장 타임존 UTC -> KST 백필.
--
-- DbWriterService.toKstLocalDateTime 이 KST 로 저장하도록 바뀌었다. 그 이전에
-- 들어온 행은 UTC 라, 안 맞추면 한 컬럼에 두 기준이 섞여 24시간 윈도우 쿼리들이
-- (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul' 기준) 어긋난다.
--
-- 대상은 전부 TIMESTAMP (without time zone) 이고 한국은 서머타임이 없어 고정 +9h 가 맞다.
--
-- 재실행하면 18시간이 더해진다. flyway repair 후 재시도할 때는 적용 여부를 먼저 확인할 것:
--   SELECT max(published_at), now() AT TIME ZONE 'Asia/Seoul' FROM article;
-- 되돌릴 때는 이 파일을 고치지 말고 V11 로 같은 값을 뺀다 (checksum).
--
-- 전체 행 UPDATE 라 테이블이 재작성된다. 적용 후 VACUUM (ANALYZE) article, issue 권장.


-- deleted_at 은 아직 앱이 쓰지 않지만 수기 처리분 대비. NULL + INTERVAL = NULL 이라 안전.
UPDATE article
SET created_at        = created_at        + INTERVAL '9 hours',
    crawled_at        = crawled_at        + INTERVAL '9 hours',
    published_at      = published_at      + INTERVAL '9 hours',
    issue_assigned_at = issue_assigned_at + INTERVAL '9 hours',
    deleted_at        = deleted_at        + INTERVAL '9 hours';


-- V6_1 은 기존 first_seen_at 을 MIN 으로 옮기기만 해서 기준이 같다.
UPDATE issue
SET first_seen_at = first_seen_at + INTERVAL '9 hours',
    created_at    = created_at    + INTERVAL '9 hours',
    updated_at    = updated_at    + INTERVAL '9 hours';


-- 제외: field/theme/users 의 created_at, updated_at 은 DEFAULT CURRENT_TIMESTAMP 로만
-- 채워지고 시간 조건에 쓰이지 않는다. country_tone, article_summary 는 쓰기 경로가 없다.
