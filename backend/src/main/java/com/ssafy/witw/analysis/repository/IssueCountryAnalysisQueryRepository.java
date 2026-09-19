package com.ssafy.witw.analysis.repository;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
@RequiredArgsConstructor
public class IssueCountryAnalysisQueryRepository {
    private static final String ISSUE_EXISTS_AT = """
            SELECT EXISTS (SELECT 1 FROM issue WHERE id = ? AND created_at <= ?)
            """;

    private static final String ANALYSIS_EXISTS_AT = """
            SELECT EXISTS (
                SELECT 1 FROM issue_country_analysis
                WHERE issue_id = ? AND country_code = ? AND created_at <= ?
            )
            """;

    private static final String LATEST_BY_ISSUE = """
            SELECT DISTINCT ON (country_code)
                   id, issue_id, country_code, title, summary, details, article_count, created_at
            FROM issue_country_analysis
            WHERE issue_id = ? AND created_at <= ?
            ORDER BY country_code, created_at DESC, id DESC
            """;

    private static final String LATEST_BY_ISSUE_AND_COUNTRY = """
            SELECT id, issue_id, country_code, title, summary, details, article_count, created_at
            FROM issue_country_analysis
            WHERE issue_id = ? AND country_code = ? AND created_at <= ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """;

    private final JdbcTemplate jdbcTemplate;

    public boolean issueExistsAt(long issueId, LocalDateTime asOf) {
        return Boolean.TRUE.equals(jdbcTemplate.queryForObject(
                ISSUE_EXISTS_AT, Boolean.class, issueId, Timestamp.valueOf(asOf)));
    }

    public boolean analysisExistsAt(long issueId, String countryCode, LocalDateTime asOf) {
        return Boolean.TRUE.equals(jdbcTemplate.queryForObject(
                ANALYSIS_EXISTS_AT, Boolean.class, issueId, countryCode, Timestamp.valueOf(asOf)));
    }

    public List<AnalysisRow> findLatestByIssue(long issueId, LocalDateTime asOf) {
        return jdbcTemplate.query(LATEST_BY_ISSUE, this::mapRow, issueId, Timestamp.valueOf(asOf));
    }

    public Optional<AnalysisRow> findLatestByIssueAndCountry(long issueId, String countryCode, LocalDateTime asOf) {
        return jdbcTemplate.query(LATEST_BY_ISSUE_AND_COUNTRY, this::mapRow,
                        issueId, countryCode, Timestamp.valueOf(asOf))
                .stream().findFirst();
    }

    private AnalysisRow mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new AnalysisRow(
                rs.getLong("id"), rs.getLong("issue_id"), rs.getString("country_code"),
                rs.getString("title"), rs.getString("summary"), rs.getString("details"),
                rs.getLong("article_count"), rs.getTimestamp("created_at").toLocalDateTime());
    }

    public record AnalysisRow(
            long id,
            long issueId,
            String countryCode,
            String title,
            String summary,
            String details,
            long articleCount,
            LocalDateTime createdAt
    ) { }
}
