CREATE TABLE issue_country_heat_score (
    id                               BIGINT GENERATED ALWAYS AS IDENTITY,
    issue_id                         BIGINT         NOT NULL,
    country_code                    VARCHAR(2)     NOT NULL,
    calculated_at                   TIMESTAMP      NOT NULL,
    score_version                   VARCHAR(20)    NOT NULL,
    local_heat_score                DECIMAL(6, 2)  NOT NULL,

    CONSTRAINT pk_issue_country_heat_score PRIMARY KEY (id),
    CONSTRAINT uk_issue_country_heat_score_snapshot
        UNIQUE (issue_id, country_code, calculated_at),
    CONSTRAINT fk_issue_country_heat_score_issue
        FOREIGN KEY (issue_id) REFERENCES issue (id) ON DELETE CASCADE,
    CONSTRAINT fk_issue_country_heat_score_country
        FOREIGN KEY (country_code) REFERENCES country (country_code),
    CONSTRAINT ck_issue_country_local_heat
        CHECK (local_heat_score BETWEEN 0 AND 100)
);

CREATE INDEX idx_issue_country_heat_country_score
    ON issue_country_heat_score (
        country_code, calculated_at DESC, local_heat_score DESC, issue_id
    );

CREATE INDEX idx_issue_country_heat_snapshot
    ON issue_country_heat_score (
        calculated_at, issue_id, local_heat_score DESC, country_code
    );


CREATE TABLE issue_global_heat_score (
    id                               BIGINT GENERATED ALWAYS AS IDENTITY,
    issue_id                         BIGINT         NOT NULL,
    calculated_at                   TIMESTAMP      NOT NULL,
    score_version                   VARCHAR(20)    NOT NULL,
    global_heat_score               DECIMAL(6, 2)  NOT NULL,
    country_count                   BIGINT         NOT NULL,

    CONSTRAINT pk_issue_global_heat_score PRIMARY KEY (id),
    CONSTRAINT uk_issue_global_heat_score_snapshot
        UNIQUE (issue_id, calculated_at),
    CONSTRAINT fk_issue_global_heat_score_issue
        FOREIGN KEY (issue_id) REFERENCES issue (id) ON DELETE CASCADE,
    CONSTRAINT ck_issue_global_heat
        CHECK (global_heat_score BETWEEN 0 AND 100)
);

CREATE INDEX idx_issue_global_heat_score_rank
    ON issue_global_heat_score (
        calculated_at DESC, global_heat_score DESC, issue_id
    );
