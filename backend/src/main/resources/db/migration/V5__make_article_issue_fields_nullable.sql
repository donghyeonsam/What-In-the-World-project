ALTER TABLE article
    ALTER COLUMN issue_similarity DROP NOT NULL,
    ALTER COLUMN issue_assigned_at DROP NOT NULL,
    ALTER COLUMN issue_assigned_at DROP DEFAULT;
