import test from 'node:test';
import assert from 'node:assert/strict';
import { datePartBounds, selectDatePart } from '../src/timeMachine/dateSelection.js';

test('ruler disables dates before September 19 and after today', () => {
  const today = '2026-09-21';
  assert.deepEqual(datePartBounds(today, 0, today), [2026, 2026]);
  assert.deepEqual(datePartBounds(today, 1, today), [9, 9]);
  assert.deepEqual(datePartBounds(today, 2, today), [19, 21]);
  assert.equal(selectDatePart(today, 2, 19, today), '2026-09-19');
  assert.equal(selectDatePart(today, 2, 18, today), today);
  assert.equal(selectDatePart(today, 2, 22, today), today);
  assert.equal(selectDatePart(today, 1, 8, today), today);
  assert.equal(selectDatePart(today, 0, 2025, today), today);
});

test('moving to an earlier month starts at its last day, within selection bounds', () => {
  assert.equal(selectDatePart('2026-10-01', 1, 9, '2026-10-01'), '2026-09-30');
  assert.equal(selectDatePart('2026-10-31', 1, 9, '2026-11-01'), '2026-09-30');
  assert.equal(selectDatePart('2027-03-01', 1, 2, '2027-03-01'), '2027-02-28');
  assert.equal(selectDatePart('2028-03-01', 1, 2, '2028-03-01'), '2028-02-29');
});

test('changing to a later month or year keeps the day within calendar and selection bounds', () => {
  assert.equal(selectDatePart('2026-09-19', 1, 10, '2026-10-31'), '2026-10-19');
  assert.equal(selectDatePart('2027-01-01', 0, 2026, '2027-06-10'), '2026-09-19');
  assert.equal(selectDatePart('2026-12-31', 0, 2027, '2027-06-10'), '2027-06-10');
  assert.equal(selectDatePart('2028-02-29', 0, 2027, '2028-03-01'), '2027-02-28');
  assert.deepEqual(datePartBounds('2028-02-01', 2, '2028-03-01'), [1, 29]);
});
