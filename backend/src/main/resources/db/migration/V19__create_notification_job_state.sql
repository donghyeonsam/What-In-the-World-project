CREATE TABLE notification_job_state (
    job_name VARCHAR(100) PRIMARY KEY,
    next_period_start TIMESTAMP NOT NULL
);

-- 최초 설치 시점이 포함된 10분 구간부터 시작한다.
-- 과거에 쌓인 기사 전체를 알림으로 보내지는 않는다.
INSERT INTO notification_job_state (
    job_name,
    next_period_start
)
VALUES (
'THEME_NOTIFICATION',
date_trunc('hour', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')
    + floor(extract(minute FROM CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') / 10) * INTERVAL '10 minutes'
 );