const DRAG_RADIANS_PER_PIXEL = 0.0045;
const MAX_YAW_SPEED = 10;
const MAX_PITCH_SPEED = 3.5;
const RELEASE_SPEED_SCALE = 0.9;
const DRAG = 0.6;
const FRICTION = 0.28;

const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));

// Keep the release speed independent of how often pointermove fires.
export function globeDragVelocity(dx, dy, elapsedMs) {
  const seconds = Math.max(elapsedMs, 1) / 1000;
  return {
    yaw: clamp(dx * DRAG_RADIANS_PER_PIXEL / seconds, MAX_YAW_SPEED),
    pitch: clamp(dy * DRAG_RADIANS_PER_PIXEL / seconds, MAX_PITCH_SPEED),
  };
}

// Average the last part of a gesture so one tiny final pointer event cannot kill a flick.
export function globeReleaseVelocity(samples, releasedAt = samples.at(-1)?.time) {
  if (samples.length < 2) return { yaw: 0, pitch: 0 };
  const last = samples[samples.length - 1];
  const age = Math.max(0, releasedAt - last.time);
  if (age >= 100) return { yaw: 0, pitch: 0 };
  let dx = 0, dy = 0, duration = 0;
  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const current = samples[index];
    const interval = current.time - previous.time;
    const overlap = current.time - Math.max(previous.time, last.time - 70);
    if (interval <= 0 || overlap <= 0) continue;
    const weight = Math.exp(-(last.time - current.time) / 30);
    dx += (current.x - previous.x) * overlap / interval * weight;
    dy += (current.y - previous.y) * overlap / interval * weight;
    duration += overlap * weight;
  }
  if (!duration) return { yaw: 0, pitch: 0 };
  const speed = globeDragVelocity(dx, dy, duration);
  const freshness = Math.max(0, 1 - Math.max(0, age - 24) / 76);
  return {
    yaw: speed.yaw * freshness * RELEASE_SPEED_SCALE,
    pitch: speed.pitch * freshness * RELEASE_SPEED_SCALE,
  };
}

// Exact integration of linear drag + gentle constant friction: strong flicks coast,
// precise adjustments settle promptly, with identical travel at different refresh rates.
function coast(speed, seconds) {
  const magnitude = Math.abs(speed);
  if (!magnitude) return { distance: 0, speed: 0 };
  const stopAt = Math.log1p(magnitude * DRAG / FRICTION) / DRAG;
  const time = Math.min(seconds, stopAt);
  const decay = Math.exp(-DRAG * time);
  const offset = FRICTION / DRAG;
  return {
    distance: Math.sign(speed) * ((magnitude + offset) * (1 - decay) / DRAG - offset * time),
    speed: seconds >= stopAt ? 0 : Math.sign(speed) * Math.max(0, (magnitude + offset) * decay - offset),
  };
}

export function advanceGlobeInertia(yaw, pitch, yawSpeed, pitchSpeed, elapsedMs, pitchLimit) {
  const seconds = Math.max(0, elapsedMs) / 1000;
  const horizontal = coast(yawSpeed, seconds);
  const vertical = coast(pitchSpeed, seconds);
  const nextPitch = clamp(pitch + vertical.distance, pitchLimit);
  return {
    yaw: yaw + horizontal.distance,
    pitch: nextPitch,
    yawSpeed: horizontal.speed,
    pitchSpeed: nextPitch === pitchLimit || nextPitch === -pitchLimit
      ? 0 : vertical.speed,
  };
}
