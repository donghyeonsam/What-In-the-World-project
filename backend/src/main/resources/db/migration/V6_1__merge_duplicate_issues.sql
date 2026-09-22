-- Run before V7 adds UNIQUE(name). Keep the lowest issue ID for each name.
-- Flyway executes this migration in one transaction.
LOCK TABLE issue, article, country_tone IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE duplicate_issue_map ON COMMIT DROP AS
SELECT id AS issue_id,
       MIN(id) OVER (PARTITION BY name) AS retained_id,
       MIN(first_seen_at) OVER (PARTITION BY name) AS first_seen_at
FROM issue
WHERE name IN (SELECT name FROM issue GROUP BY name HAVING COUNT(*) > 1);

-- Merge snapshots only when both calculation time and country match.
-- tone_sd is a population standard deviation (STDDEV_POP).
CREATE TEMP TABLE merged_issue_country_tone ON COMMIT DROP AS
SELECT ct.calculated_at,
       m.retained_id AS issue_id,
       ct.country_code,
       COALESCE(SUM(ct.article_count * ct.tone_avg)
                / NULLIF(SUM(ct.article_count), 0), 0) AS tone_avg,
       SQRT(GREATEST(COALESCE(
           SUM(ct.article_count * (ct.tone_sd * ct.tone_sd + ct.tone_avg * ct.tone_avg))
               / NULLIF(SUM(ct.article_count), 0)
           - POWER(SUM(ct.article_count * ct.tone_avg)
               / NULLIF(SUM(ct.article_count), 0), 2), 0), 0)) AS tone_sd,
       SUM(ct.article_count)::BIGINT AS article_count
FROM country_tone ct
JOIN duplicate_issue_map m ON m.issue_id = ct.issue_id
GROUP BY ct.calculated_at, m.retained_id, ct.country_code;

DELETE FROM country_tone ct
USING duplicate_issue_map m
WHERE ct.issue_id = m.issue_id;

INSERT INTO country_tone
    (calculated_at, issue_id, country_code, tone_avg, tone_sd, article_count)
SELECT calculated_at, issue_id, country_code, tone_avg, tone_sd, article_count
FROM merged_issue_country_tone;

UPDATE article a
SET issue_id = m.retained_id
FROM duplicate_issue_map m
WHERE a.issue_id = m.issue_id
  AND m.issue_id <> m.retained_id;

UPDATE issue i
SET first_seen_at = m.first_seen_at
FROM duplicate_issue_map m
WHERE i.id = m.issue_id
  AND m.issue_id = m.retained_id;

DELETE FROM issue i
USING duplicate_issue_map m
WHERE i.id = m.issue_id
  AND m.issue_id <> m.retained_id;
