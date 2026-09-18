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
    .multiplyScalar(1.025 + Math.sin(Math.PI * t)
      * Math.min(0.225, angle * (0.2 - Math.min(1, angle / 1.5) * 0.1)));
  return curve;
}

export function createMentionGroup(links) {
  const group = new THREE.Group();
  const time = { value: 0 };
  group.userData.flowTime = time;
  for (const link of links) {
    const color = link.incoming ? 0xffb454 : 0x6fe7ff;
    const curve = mentionCurve(link.from, link.to);
    const radius = 0.0032 + Math.sqrt(link.ratio) * 0.0045;
    // 곡선은 from → to 순서. 두 색 모두 UV의 양의 방향으로 흐르면 언급 방향과 일치한다.
    // 프레임마다 지오메트리를 재생성하지 않고 그룹 공용 시간 uniform 하나만 갱신한다.
    const material = new THREE.ShaderMaterial({
      uniforms: {
        flowTime: time, color: { value: new THREE.Color(color) },
        opacity: { value: 0.78 + Math.sqrt(link.ratio) * 0.2 },
      },
      transparent: true,
      depthWrite: false,
      vertexShader: `varying float vProgress;
        void main() {
          vProgress = uv.x;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }`,
      fragmentShader: `uniform float flowTime;
        uniform vec3 color;
        uniform float opacity;
        varying float vProgress;
        void main() {
          if (fract(vProgress * 12.0 - flowTime * 0.65) > 0.72) discard;
          gl_FragColor = vec4(color, opacity);
          #include <encodings_fragment>
        }`,
    });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, radius, 5, false), material);
    mesh.userData = { type: 'mention', ...link };
    group.add(mesh);
    const arrow = new THREE.Mesh(new THREE.ConeGeometry(radius * 3, 0.035, 8), new THREE.MeshBasicMaterial({ color }));
    arrow.position.copy(curve.getPoint(0.94));
    arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), curve.getTangent(0.94).normalize());
    arrow.userData = { type: 'mention', ...link };
    group.add(arrow);
  }
  return group;
}

export function updateMentionFlow(group, elapsedSeconds, reducedMotion = false) {
  if (group.userData.flowTime) group.userData.flowTime.value = reducedMotion ? 0 : elapsedSeconds;
}
