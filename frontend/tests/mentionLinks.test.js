import test from 'node:test';
import assert from 'node:assert/strict';
import { mentionLinks, mentionCurve, createMentionGroup } from '../src/lib/mentionLinks.js';

const countries = [
  { code: 'US', lat: 38, lon: -97 }, { code: 'JP', lat: 36.2, lon: 138.3 },
];
const data = {
  countryCode: 'US', countryName: '미국',
  sourceMentions: [{ countryCode: 'CN', countryName: '중국', mentionRatio: .12 },
    { countryCode: 'IR', countryName: '이란', mentionRatio: .11 },
    { countryCode: 'RU', countryName: '러시아', mentionRatio: .06 },
    { countryCode: 'CA', countryName: '캐나다', mentionRatio: .04 }],
  targetMentions: [{ countryCode: 'JP', countryName: '일본', mentionRatio: .8 }],
};
test('source means selected country -> other; target means other -> selected', () => {
  const outgoing = mentionLinks(data, 'outgoing', countries);
  assert.equal(outgoing.length, 3);
  assert.equal(outgoing[0].fromName, '미국');
  assert.equal(outgoing[0].toName, '중국');
  assert.equal(outgoing[0].ratio, .12);
  const incoming = mentionLinks(data, 'incoming', countries)[0];
  assert.equal(incoming.fromName, '일본');
  assert.equal(incoming.toName, '미국');
  assert.equal(incoming.incoming, true);
});
test('invalid, self and unknown-coordinate rows do not invent connections', () => {
  assert.deepEqual(mentionLinks(null, 'outgoing', countries), []);
  assert.deepEqual(mentionLinks({ ...data, sourceMentions: [
    { countryCode: 'US', mentionRatio: .4 }, { countryCode: 'ZZ', mentionRatio: .2 },
    { countryCode: 'CN', mentionRatio: null }, { countryCode: 'IR', mentionRatio: -1 },
  ] }, 'outgoing', countries), []);
});
test('curves follow the globe above the surface, including date-line and antipodal routes', () => {
  for (const [from, to] of [[countries[0], countries[1]],
    [{ lat: 0, lon: 179 }, { lat: 0, lon: -179 }],
    [{ lat: 0, lon: 0 }, { lat: 0, lon: 180 }]]) {
    const curve = mentionCurve(from, to);
    assert.ok(Math.abs(curve.getPoint(0).length() - 1.025) < 1e-9);
    assert.ok(Math.abs(curve.getPoint(1).length() - 1.025) < 1e-9);
    for (const point of curve.getPoints(64)) {
      assert.ok(point.toArray().every(Number.isFinite));
      assert.ok(point.length() >= 1.0249);
    }
  }
});
test('solid cyan and dashed amber groups use different shapes with real directional arrow data', () => {
  const outgoing = createMentionGroup(mentionLinks(data, 'outgoing', countries));
  const incoming = createMentionGroup(mentionLinks(data, 'incoming', countries));
  assert.equal(outgoing.children.length, 6);
  assert.equal(incoming.children.length, 13);
  assert.equal(outgoing.children[0].material.color.getHex(), 0x6fe7ff);
  assert.equal(incoming.children[0].material.color.getHex(), 0xffb454);
  assert.equal(incoming.children.at(-1).userData.toName, '미국');
  for (const group of [outgoing, incoming]) group.traverse((mesh) => {
    mesh.geometry?.dispose(); mesh.material?.dispose();
  });
});
