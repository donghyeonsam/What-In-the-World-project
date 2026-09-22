import test from 'node:test';
import assert from 'node:assert/strict';
import { issueCardSlots, placeIssueCards } from '../src/lib/issueCardLayout.js';

test('edge cards fit without overlaps and leave room for satellite, clock, and legend', () => {
  for (const [width, height] of [[900, 900], [716, 650], [520, 600], [360, 400]]) {
    const cardWidth = Math.min(205, (width - 36) / 2), cardHeight = 90;
    const satelliteBottom = width < 500 ? 198 : 212;
    const slots = issueCardSlots({ width, height, cardWidth, cardHeight, satelliteBottom });
    assert.ok(slots.length > 0 && slots.length <= 8);
    slots.forEach((slot, index) => {
      assert.ok(slot.x >= 0 && slot.x + cardWidth <= width);
      assert.ok(slot.y >= 110 && slot.y + cardHeight <= height - 115);
      if (slot.x > width / 2) assert.ok(slot.y >= satelliteBottom + 12);
      slots.slice(index + 1).forEach((other) => {
        const overlaps = slot.x < other.x + cardWidth && slot.x + cardWidth > other.x
          && slot.y < other.y + cardHeight && slot.y + cardHeight > other.y;
        assert.equal(overlaps, false);
      });
    });
  }
});

test('large stages show eight ranked cards; short stages lower the cap', () => {
  const dimensions = { width: 900, cardWidth: 205, cardHeight: 90, satelliteBottom: 212 };
  assert.equal(issueCardSlots({ ...dimensions, height: 900 }).length, 8);
  assert.ok(issueCardSlots({ ...dimensions, height: 450 }).length < 8);
});

test('selecting an already visible country does not exchange card identities or positions', () => {
  const config = { width: 900, height: 900, cardWidth: 205, cardHeight: 90, satelliteBottom: 212 };
  const rows = [{ id: 'kr', x: 650, y: 420, back: false }, { id: 'us', x: 210, y: 440, back: true }];
  const input = { ...config, rows, slots: issueCardSlots(config) };
  assert.deepEqual(placeIssueCards({ ...input, selectedId: 'us' }), placeIssueCards(input));
  const result = placeIssueCards(input);
  assert.ok(result.find((card) => card.id === 'kr').x > 450);
  assert.ok(result.find((card) => card.id === 'us').x < 450);
});

test('geographic placement retains the cap, avoids overlaps and includes an outside selection', () => {
  const config = { width: 900, height: 900, cardWidth: 205, cardHeight: 90, satelliteBottom: 212 };
  const obstacle = { x: 668, y: 20, width: 220, height: 192 };
  const rows = Array.from({ length: 12 }, (_, i) => ({ id: String(i), x: 700, y: 190 + i * 10, back: i % 3 === 0 }));
  const cards = placeIssueCards({ ...config, rows, slots: issueCardSlots(config), selectedId: '11', obstacles: [obstacle] });
  assert.deepEqual(cards.map((card) => card.id), ['0', '1', '2', '3', '4', '5', '6', '11']);
  cards.forEach((card, i) => {
    assert.ok(card.x >= 0 && card.x + card.width <= config.width);
    assert.ok(card.y >= 110 && card.y + card.height <= config.height - 115);
    [...cards.slice(i + 1), obstacle].forEach((other) => {
      assert.equal(card.x < other.x + other.width && card.x + card.width > other.x
        && card.y < other.y + other.height && card.y + card.height > other.y, false);
    });
  });
});
