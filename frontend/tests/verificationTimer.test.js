import test from 'node:test';
import assert from 'node:assert/strict';
import { remainingSeconds } from '../src/personalization/useVerificationTimer.js';

test('verification timer uses elapsed time including background-tab gaps and never goes negative', () => {
  const start = 1000;
  const deadline = start + 300_000;
  assert.equal(remainingSeconds(deadline, start), 300);
  assert.equal(remainingSeconds(deadline, start + 1000), 299);
  assert.equal(remainingSeconds(deadline, start + 240_000), 60);
  assert.equal(remainingSeconds(deadline, deadline - 1), 1);
  assert.equal(remainingSeconds(deadline, deadline), 0);
  assert.equal(remainingSeconds(deadline, deadline + 60_000), 0);
});
