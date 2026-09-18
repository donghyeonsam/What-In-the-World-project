import test from 'node:test';
import assert from 'node:assert/strict';
import { issueToneDeviation } from '../src/data/issuePerspective.js';

const row = (code, count, mean, sd) => ({ country: { countryCode: code }, articleCount: count, toneAvg: mean, toneSd: sd });
test('pooled deviation matches raw articles across unequal country groups', () => {
  // KR: [0, 20], US: [60, 80, 100].
  const raw = [0, 20, 60, 80, 100];
  const mean = raw.reduce((sum, value) => sum + value, 0) / raw.length;
  const expected = Math.sqrt(raw.reduce((sum, value) => sum + (value - mean) ** 2, 0) / raw.length) / 50;
  const actual = issueToneDeviation([row('KR', 2, 10, 10), row('US', 3, 80, Math.sqrt(800 / 3))]);
  assert.ok(Math.abs(actual - expected) < 1e-12);
});
test('missing variance is not invented; singleton groups can be combined', () => {
  assert.equal(issueToneDeviation([row('KR', 2, 50, null)]), null);
  assert.equal(issueToneDeviation([row('KR', 1, 50, 0)]), null);
  assert.equal(issueToneDeviation([row('KR', 1, 0, null), row('US', 1, 100, null)]), 1);
  assert.equal(issueToneDeviation([]), null);
});
