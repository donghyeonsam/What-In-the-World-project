import { scoreOf } from './responseAdapters.js';

export function rankIssueCountries(rows = []) {
  return rows.filter((row) => row.country?.countryCode && Number(row.articleCount) > 0)
    .slice().sort((a, b) => b.articleCount - a.articleCount
      || a.country.countryCode.localeCompare(b.country.countryCode));
}

// Frontend integration contract: one analysis per country from the issue detail response.
// The backend must select the latest analysis at/before asOf for historical requests.
export function issueCountryPerspectives(data = {}) {
  const analyses = new Map((data.countryAnalyses || []).map((analysis) => [
    analysis.countryCode?.toUpperCase(), analysis,
  ]));
  return rankIssueCountries(data.countryTones).map((row) => ({
    ...row,
    analysis: analyses.get(row.country.countryCode.toUpperCase()) || null,
  }));
}
export function issueMetrics(rows = []) {
  const ranked = rankIssueCountries(rows);
  const scored = ranked.filter((row) => row.toneAvg != null && Number.isFinite(Number(row.toneAvg)));
  const count = scored.reduce((sum, row) => sum + Number(row.articleCount), 0);
  return {
    articleCount: ranked.reduce((sum, row) => sum + Number(row.articleCount), 0),
    countryCount: ranked.length,
    score: count ? scoreOf(scored.reduce((sum, row) => sum + Number(row.toneAvg) * Number(row.articleCount), 0) / count) : null,
  };
}
