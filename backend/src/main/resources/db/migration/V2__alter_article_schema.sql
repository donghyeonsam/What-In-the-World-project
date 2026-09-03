-- 1. article_country_mention -> article FK 제약조건 먼저 제거
ALTER TABLE article_country_mention
DROP CONSTRAINT fk_article_to_article_country_mention;

-- 2. article.uuid 컬럼 삭제
ALTER TABLE article DROP COLUMN uuid;

-- 3. article.id의 identity 속성 제거
ALTER TABLE article ALTER COLUMN id DROP IDENTITY IF EXISTS;

-- 4. article.id 타입 변경 (bigint -> varchar)
ALTER TABLE article ALTER COLUMN id TYPE VARCHAR(255) USING id::VARCHAR(255);

-- 5. 참조하는 쪽(article_country_mention.article_id)도 타입 맞춰서 변경
ALTER TABLE article_country_mention
ALTER COLUMN article_id TYPE VARCHAR(255) USING article_id::VARCHAR(255);

-- 6. FK 제약조건 재생성
ALTER TABLE article_country_mention
    ADD CONSTRAINT fk_article_to_article_country_mention
        FOREIGN KEY (article_id) REFERENCES article (id);