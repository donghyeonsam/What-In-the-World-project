import test from 'node:test';
import assert from 'node:assert/strict';
import { advanceGlobeInertia, globeDragVelocity, globeReleaseVelocity } from '../src/lib/globeInertia.js';

test('a quick drag glides after release and settles instead of spinning forever', () => {
  const speed = globeDragVelocity(25, 0, 16);
  assert.ok(speed.yaw > 5 && speed.yaw <= 10);
  let state = { yaw: 0, pitch: 0, yawSpeed: speed.yaw, pitchSpeed: speed.pitch };
  for (let frame = 0; frame < 60; frame += 1) {
    state = advanceGlobeInertia(state.yaw, state.pitch, state.yawSpeed,
      state.pitchSpeed, 16, 0.9);
  }
  assert.ok(state.yawSpeed > 1.3);
  for (let frame = 0; frame < 650; frame += 1) {
    state = advanceGlobeInertia(state.yaw, state.pitch, state.yawSpeed,
      state.pitchSpeed, 16, 0.9);
  }
  assert.ok(state.yaw > Math.PI * 2 && state.yaw < Math.PI * 4);
  assert.equal(state.yawSpeed, 0);
});

test('release speed uses the recent gesture, not a tiny last pointer event', () => {
  const samples = [
    { x: 0, y: 0, time: 0 },
    { x: 20, y: 0, time: 16 },
    { x: 40, y: 0, time: 32 },
    { x: 41, y: 0, time: 48 },
  ];
  assert.ok(globeReleaseVelocity(samples).yaw > globeDragVelocity(1, 0, 16).yaw);
  assert.deepEqual(globeReleaseVelocity([]), { yaw: 0, pitch: 0 });
});

test('release carries actual gesture speed into the glide without an artificial boost', () => {
  const fast = globeReleaseVelocity([
    { x: 0, y: 0, time: 0 }, { x: 25, y: 0, time: 16 },
  ]);
  const slow = globeReleaseVelocity([
    { x: 0, y: 0, time: 0 }, { x: 2, y: 0, time: 30 },
  ]);
  assert.ok(Math.abs(fast.yaw - 25 * 0.0045 / 0.016) < 1e-10);
  assert.equal(slow.yaw, globeDragVelocity(2, 0, 30).yaw);
});

test('pausing before release brakes the globe and gentle movements settle quickly', () => {
  const samples = [{ x: 0, y: 0, time: 0 }, { x: 80, y: 0, time: 40 }];
  assert.deepEqual(globeReleaseVelocity(samples, 150), { yaw: 0, pitch: 0 });
  assert.ok(globeReleaseVelocity(samples, 100).yaw < globeReleaseVelocity(samples, 40).yaw);
  const settled = advanceGlobeInertia(0, 0, 0.3, 0, 1000, 0.9);
  assert.equal(settled.yawSpeed, 0);
  assert.ok(settled.yaw < 0.15);
});

test('a recent reversal wins over the earlier direction', () => {
  const velocity = globeReleaseVelocity([
    { x: 0, y: 0, time: 0 }, { x: 40, y: 0, time: 40 },
    { x: 10, y: 0, time: 60 }, { x: -20, y: 0, time: 80 },
  ]);
  assert.ok(velocity.yaw < 0);
});

test('inertia is frame-rate independent and stops at the pitch limit', () => {
  const fast = advanceGlobeInertia(0, 0, 1, 1, 32, 0.9);
  const first = advanceGlobeInertia(0, 0, 1, 1, 16, 0.9);
  const second = advanceGlobeInertia(first.yaw, first.pitch, first.yawSpeed,
    first.pitchSpeed, 16, 0.9);
  assert.ok(Math.abs(fast.yaw - second.yaw) < 1e-10);
  assert.ok(Math.abs(fast.pitch - second.pitch) < 1e-10);
  const limited = advanceGlobeInertia(0, 0.89, 0, 1.6, 50, 0.9);
  assert.equal(limited.pitch, 0.9);
  assert.equal(limited.pitchSpeed, 0);
});
