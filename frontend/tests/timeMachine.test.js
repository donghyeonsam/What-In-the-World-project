import test from 'node:test';
import assert from 'node:assert/strict';
import { destinationTime, koreaDate, readAsOf, stageTimeLabel, travelDirection } from '../src/timeMachine/timeMachine.js';
import { api } from '../src/data/api.js';
import { httpNewsSource } from '../src/news/newsSource.js';

test('time travel spins toward newer dates and reverses toward older dates', () => {
  const departed = Date.parse('2026-09-22T00:00:00Z');
  assert.equal(travelDirection({ origin: null, target: '2026-09-15T00:00:00Z', departed }), -1);
  assert.equal(travelDirection({ origin: '2026-09-15T00:00:00Z', target: '2026-09-10T00:00:00Z', departed }), -1);
  assert.equal(travelDirection({ origin: '2026-09-10T00:00:00Z', target: '2026-09-15T00:00:00Z', departed }), 1);
  assert.equal(travelDirection({ origin: '2026-09-10T00:00:00Z', target: null, departed }), 1);
});

test('date selection preserves the current Korean clock, independent of browser timezone', () => {
  const now = new Date('2026-09-17T01:50:23.456Z');
  assert.equal(destinationTime('2026-09-06', now), '2026-09-06T01:50:23.456Z');
  assert.equal(destinationTime('2026-09-10', now), '2026-09-10T01:50:23.456Z');
  const nearMidnight = new Date('2026-09-16T16:30:00Z');
  assert.equal(koreaDate(nearMidnight), '2026-09-17');
  assert.equal(destinationTime('2026-09-06', nearMidnight), '2026-09-05T16:30:00.000Z');
});

test('stage clock displays Korean year, date and minutes across UTC midnight', () => {
  assert.equal(stageTimeLabel('2026-09-16T16:30:42Z'), '2026년 9월 17일 1시 30분');
  assert.equal(stageTimeLabel('2026-09-17T04:05:00Z'), '2026년 9월 17일 13시 05분');
});

test('start boundary, future dates and invalid dates are rejected', () => {
  const now = new Date('2026-10-01T01:50:00Z');
  for (const date of ['2026-09-05', '2026-10-02', '2026-09-31', '', 'invalid']) {
    assert.equal(destinationTime(date, now), null);
  }
});

test('the currently displayed date cannot be selected as a destination', () => {
  const now = new Date('2026-09-17T01:50:00Z');
  assert.equal(destinationTime('2026-09-17', now), null);
  assert.equal(destinationTime('2026-09-10', now, new Date('2026-09-10T01:50:00Z')), null);
});

test('shared URLs restore the same instant and invalid URLs return to live mode', () => {
  const now = new Date('2026-09-17T01:50:00Z');
  assert.equal(readAsOf('?asOf=2026-09-10T10%3A50%3A00%2B09%3A00', now), '2026-09-10T01:50:00.000Z');
  for (const value of ['invalid', '2026-09-10T10:50:00', '2026-09-18T00:00:00Z', '2026-09-05T00:00:00Z']) {
    assert.equal(readAsOf(`?${new URLSearchParams({ asOf: value })}`, now), null);
  }
});

test('all twelve content requests receive the identical asOf and returning live removes it', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(new URL(url, 'http://localhost'));
    return new Response(JSON.stringify({ status: 200, data: [] }));
  };
  const asOf = '2026-09-10T01:50:00.000Z';
  try {
    await api.dashboard(undefined, asOf);
    await api.fields(undefined, asOf);
    await api.country('KR', undefined, asOf);
    await api.popular('KR', undefined, asOf);
    await api.theme(1, 'KR', undefined, asOf);
    await api.issue(1, undefined, asOf);
    await api.overview(1, 'KR', undefined, asOf);
    await api.countryAnalyses(1, undefined, asOf);
    await api.countryAnalysis(1, 'kr', undefined, asOf);
    await httpNewsSource.filters({ asOf });
    await httpNewsSource.list({ page: 1 }, { asOf });
    await httpNewsSource.detail('a', { asOf });
    assert.equal(calls.length, 12);
    assert.ok(calls.every((url) => url.searchParams.get('asOf') === asOf));
    await api.dashboard(undefined, null);
    assert.equal(calls.at(-1).searchParams.has('asOf'), false);
    await api.countryAnalyses(1, undefined, null);
    assert.equal(calls.at(-1).searchParams.has('asOf'), false);
    await api.countryAnalysis(1, 'KR', undefined, null);
    assert.equal(calls.at(-1).searchParams.has('asOf'), false);
  } finally { globalThis.fetch = original; }
});
