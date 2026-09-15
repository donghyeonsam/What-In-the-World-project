import * as THREE from 'three';

// 국가를 화면에 꽉 채우지 않고 주변 지역이 보이도록 한다.
export const COUNTRY_FOCUS_FILL = 0.5;
export const MIN_COUNTRY_CAMERA_Z = 1.9;

const relativeLon = (lon, center) => ((lon - center + 540) % 360) - 180;

function containsCenter(ring, lat, lon) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const x1 = relativeLon(ring[i][0], lon);
    const x2 = relativeLon(ring[j][0], lon);
    const y1 = ring[i][1];
    const y2 = ring[j][1];
    if ((y1 > lat) !== (y2 > lat) && 0 < x1 + ((lat - y1) * (x2 - x1)) / (y2 - y1)) {
      inside = !inside;
    }
  }
  return inside;
}

// 중심을 포함하는 본토를 우선한다. 중심이 바다에 있으면 가장 가까운 섬을 쓴다.
export function focusRingOf(rings, lat, lon) {
  const valid = rings.filter((ring) => ring.length >= 3);
  const mainland = valid.find((ring) => containsCenter(ring, lat, lon));
  if (mainland) return mainland;
  const lonScale = Math.cos(THREE.MathUtils.degToRad(lat));
  const distance = (ring) => Math.min(...ring.map(([lo, la]) =>
    (relativeLon(lo, lon) * lonScale) ** 2 + (la - lat) ** 2));
  return valid.reduce((closest, ring) =>
    !closest || distance(ring) < distance(closest) ? ring : closest, null);
}

export function countryCameraZ({ rings, lat, lon, pitch, yaw, fov, aspect, maxZ }) {
  const ring = focusRingOf(rings, lat, lon);
  if (!ring || !(aspect > 0)) return maxZ;
  const verticalTan = Math.tan(THREE.MathUtils.degToRad(fov / 2));
  const horizontalTan = verticalTan * aspect;
  const rotation = new THREE.Euler(pitch, yaw, 0);
  let distance = MIN_COUNTRY_CAMERA_Z;
  ring.forEach(([lo, la]) => {
    const phi = THREE.MathUtils.degToRad(90 - la);
    const theta = THREE.MathUtils.degToRad(lo + 180);
    // 강조된 윤곽선의 반지름(1.008 * 1.035)도 포함한다.
    const radius = 1.008 * 1.035;
    const point = new THREE.Vector3(
      -radius * Math.sin(phi) * Math.cos(theta),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.sin(theta),
    ).applyEuler(rotation);
    distance = Math.max(distance, point.z + Math.max(
      Math.abs(point.x) / (horizontalTan * COUNTRY_FOCUS_FILL),
      Math.abs(point.y) / (verticalTan * COUNTRY_FOCUS_FILL),
    ));
  });
  return Math.min(maxZ, distance);
}
