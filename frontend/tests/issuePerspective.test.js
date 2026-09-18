import test from 'node:test';
import assert from 'node:assert/strict';
import { rankIssueCountries, issueMetrics } from '../src/data/issuePerspective.js';
const row = (code, count, toneAvg) => ({ country: { countryCode: code }, articleCount: count, toneAvg });
test('ranking skips empty countries and resolves ties deterministically without mutating input', () => {
  const input = [row('US', 0, 50), row('KR', 4, 70), row('GB', 4, 30), row('JP', 8, null)];
  assert.deepEqual(rankIssueCountries(input).map((r) => r.country.countryCode), ['JP', 'GB', 'KR']);
  assert.equal(input[0].country.countryCode, 'US');
});
test('metrics weight scored articles and keep missing tone out of the denominator', () => {
  assert.deepEqual(issueMetrics([row('KR', 30, 100), row('US', 10, 0), row('JP', 60, null)]), { articleCount: 100, countryCount: 3, score: .5 });
  assert.equal(issueMetrics([row('JP', 10, null)]).score, null);
  assert.deepEqual(issueMetrics([]), { articleCount: 0, countryCount: 0, score: null });
});
