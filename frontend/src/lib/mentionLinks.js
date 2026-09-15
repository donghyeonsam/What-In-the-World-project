import * as THREE from 'three';

// 관계선 전용 지리 정보. 분석 대상 국가나 서버 통계에는 추가하지 않는다.
const extraLocations = {
  CN: { lat: 35, lon: 103 }, IR: { lat: 32, lon: 54 },
  RU: { lat: 61, lon: 100 }, CA: { lat: 56, lon: -106 },
};

export function mentionLinks(data, direction, countries, limit = 3) {
  if (!data) return [];
  const locations = { ...extraLocations, ...Object.fromEntries(countries.map((c) => [c.code, c])) };
  const selected = locations[data.countryCode?.toUpperCase()];
  if (!selected) return [];
  const incoming = direction === 'incoming';
  return [...(incoming ? data.targetMentions : data.sourceMentions) || []]
    .filter((row) => Number.isFinite(row.mentionRatio) && row.mentionRatio > 0
      && row.countryCode?.toUpperCase() !== data.countryCode?.toUpperCase())
    .sort((a, b) => b.mentionRatio - a.mentionRatio).slice(0, limit)
    .flatMap((row) => {
      const other = locations[row.countryCode?.toUpperCase()];
      if (!other) return [];
      return [{
        from: incoming ? other : selected, to: incoming ? selected : other,
        fromName: incoming ? row.countryName : data.countryName,
        toName: incoming ? data.countryName : row.countryName,
        ratio: Math.min(1, row.mentionRatio), incoming,
      }];
    });
}

function locationVector({ lat, lon }) {
  const phi = (90 - lat) * Math.PI / 180;
  const theta = (lon + 180) * Math.PI / 180;
  return new THREE.Vector3(-Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta));
}

export function mentionCurve(from, to) {
  const start = locationVector(from), end = locationVector(to);
  const angle = start.angleTo(end);
  let tangent = end.clone().addScaledVector(start, -start.dot(end));
  if (tangent.lengthSq() < 1e-10) {
    tangent = new THREE.Vector3(0, 1, 0).cross(start);
    if (tangent.lengthSq() < 1e-10) tangent.set(1, 0, 0);
  }
  tangent.normalize();
  const curve = new THREE.Curve();
  curve.getPoint = (t, target = new THREE.Vector3()) => target.copy(start)
    .multiplyScalar(Math.cos(angle * t)).addScaledVector(tangent, Math.sin(angle * t))
    .multiplyScalar(1.025 + Math.sin(Math.PI * t) * Math.min(0.45, angle * 0.2));
  return curve;
}

export function createMentionGroup(links) {
  const group = new THREE.Group();
  for (const link of links) {
    const color = link.incoming ? 0xffb454 : 0x6fe7ff;
    const curve = mentionCurve(link.from, link.to);
    const radius = 0.0025 + Math.sqrt(link.ratio) * 0.004;
    // 점선도 튜브로 만들어 WebGL의 1px 선 굵기 제한을 피한다.
    const segments = link.incoming ? 12 : 1;
    for (let i = 0; i < segments; i++) {
      const segment = new THREE.Curve();
      segment.getPoint = (t, target) => curve.getPoint((i + t * (link.incoming ? 0.65 : 1)) / segments, target);
      const mesh = new THREE.Mesh(new THREE.TubeGeometry(segment, link.incoming ? 5 : 64, radius, 5, false),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.65 + Math.sqrt(link.ratio) * 0.3 }));
      mesh.userData = { type: 'mention', ...link };
      group.add(mesh);
    }
    const arrow = new THREE.Mesh(new THREE.ConeGeometry(radius * 3, 0.035, 8), new THREE.MeshBasicMaterial({ color }));
    arrow.position.copy(curve.getPoint(0.94));
    arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), curve.getTangent(0.94).normalize());
    arrow.userData = { type: 'mention', ...link };
    group.add(arrow);
  }
  return group;
}
