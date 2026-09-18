CREATE TABLE user_interest_theme (
            user_id BIGINT NOT NULL,
            theme_id BIGINT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
-- 같은 사용자가 같은 테마를 두 번 이상 등록하는 것을 막기 위한 설계
            CONSTRAINT PK_USER_INTEREST_THEME PRIMARY KEY (user_id, theme_id),

            CONSTRAINT FK_USERS_TO_USER_INTEREST_THEME
                FOREIGN KEY (user_id) REFERENCES users  (id),

            CONSTRAINT FK_THEME_TO_USER_INTEREST_THEME
                FOREIGN KEY (theme_id) REFERENCES theme (id)
);