ALTER TABLE issue
    ADD COLUMN last_active_at TIMESTAMP NULL;

-- 기존 이슈는 마지막 기사 배정 시각을 활동 시각으로 사용한다. 기사 배정 이력이
-- 없거나 더 오래된 경우에는 이슈 자체의 마지막 갱신 시각을 보존한다.
UPDATE issue i
SET last_active_at = GREATEST(
        i.created_at,
        i.updated_at,
        COALESCE(
            (SELECT MAX(a.issue_assigned_at)
             FROM article a
             WHERE a.issue_id = i.id),
            i.created_at
        )
    );

ALTER TABLE issue
    ALTER COLUMN last_active_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul'),
    ALTER COLUMN last_active_at SET NOT NULL;

CREATE INDEX idx_issue_theme_last_active
    ON issue (theme_id, last_active_at DESC)
    WHERE embedding IS NOT NULL;
