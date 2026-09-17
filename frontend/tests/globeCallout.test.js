import test from 'node:test';
import assert from 'node:assert/strict';
import { layoutGlobeCallout } from '../src/lib/globeCallout.js';

test('the preferred side follows the country and the leader ends at the card edge', () => {
  const placement = layoutGlobeCallout({
    x: 550, y: 350, width: 320, height: 180,
    stageWidth: 1150, stageHeight: 700, preferRight: true, latitude: 36,
  });
  assert.equal(placement.cardX, 582);
  assert.equal(placement.lineX, placement.cardX);
  assert.ok(placement.lineY >= placement.cardY && placement.lineY <= placement.cardY + 180);
});

test('a country near the right edge moves its card to the left', () => {
  const placement = layoutGlobeCallout({
    x: 1080, y: 350, width: 320, height: 180,
    stageWidth: 1150, stageHeight: 700, preferRight: true, latitude: 36,
  });
  assert.equal(placement.cardX, 728);
  assert.equal(placement.lineX, 1048);
});

test('a narrow stage keeps the card inside its edges', () => {
  const placement = layoutGlobeCallout({
    x: 190, y: 160, width: 300, height: 160,
    stageWidth: 390, stageHeight: 420, preferRight: true, latitude: 36,
  });
  assert.ok(placement.cardX >= 16 && placement.cardX + 300 <= 374);
  assert.ok(placement.cardY >= 16 && placement.cardY + 160 <= 404);
  assert.ok(placement.lineX >= placement.cardX && placement.lineX <= placement.cardX + 300);
});
