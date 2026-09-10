import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { toneRGB, NO_SAMPLE, rgbHex } from '../../lib/tone.js';
import { shortLon, prefersReducedMotion } from '../../lib/format.js';
import s from './GlobeThree.module.css';

const GEO_URL =
  'https://raw.githubusercontent.com/vasturiano/globe.gl/master/example/datasets/ne_110m_admin_0_countries.geojson';

/* GeoJSON이 아직 없을 때 국가 외곽선 대신 그리는 근사 원의 반지름(도) */
const FALLBACK_RAD = { kr: 2.6, us: 12, uk: 4, au: 14, me: 3.2, af: 7, br: 13 };

const CYAN = 0x6fe7ff;
const AMBER = 0xffb454;
const IDLE_CAMERA_Z = 3.7;
const FOCUS_FILL_RATIO = 0.88;
const VISIBLE_GLOBE_RADIUS = 1.04;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

/** 위경도 → 구면 좌표 */
function ll2v(lat, lon, r = 1) {
  const ph = ((90 - lat) * Math.PI) / 180;
  const th = ((lon + 180) * Math.PI) / 180;
  return new THREE.Vector3(
    -r * Math.sin(ph) * Math.cos(th),
    r * Math.cos(ph),
    r * Math.sin(ph) * Math.sin(th),
  );
}

/* 손으로 끌 때의 피치 한계(rad). 포커스도 같은 값을 쓴다 — 두 길이 같은 자세를 만들어야 한다. */
const PITCH_LIMIT = 0.9;

/**
 * 나라를 카메라 정면(+Z)에 세우는 목표 회전.
 * 요(Y)로 경도를 돌리고 피치(X)로 위도를 들어 올린다. 롤(Z)은 0이다.
 *
 * 예전에는 최단호 회전(`setFromUnitVectors`)으로 한 번에 돌렸다. 나라는 가운데 오지만
 * 그 회전에는 롤이 섞인다 — 한국을 누르면 지도가 시계방향으로 90°쯤 누워서
 * 서쪽(UAE·카타르)이 위에 붙은, 세계지도와 다른 그림이 됐다.
 * 드래그(`onMove`)도 요·피치만 건드리므로 포커스만 롤을 만들 이유가 없다.
 *
 * 요가 `-(lon + 90)`인 이유는 `ll2v` 때문이다 — 회전 0에서 카메라를 보는 경도가 −90°다.
 */
function orientTo(lat, lon) {
  const pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, (lat * Math.PI) / 180));
  const yaw = (-(lon + 90) * Math.PI) / 180;
  return { pitch, yaw };
}

const shortestAngle = (from, to) => Math.atan2(Math.sin(to - from), Math.cos(to - from));

/** 방사형 글로우 스프라이트용 캔버스 텍스처 */
function glowTex() {
  const c = document.createElement('canvas');
  c.width = 64;
  c.height = 64;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.35, 'rgba(255,255,255,.4)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g;
  x.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

/** 국가명 라벨 스프라이트용 텍스처.
    바탕이 희므로 글자를 어둡게 쓰고 흰 외곽선을 둘러, 바다 위든 흰 여백 위든 읽히게 한다. */
function labelTex(text) {
  const cv = document.createElement('canvas');
  const ctx = cv.getContext('2d');
  cv.width = 256;
  cv.height = 72;
  ctx.font = '700 24px Pretendard, IBM Plex Sans KR, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.lineWidth = 6;
  ctx.lineJoin = 'round';
  ctx.strokeStyle = 'rgba(255,255,255,.92)';
  ctx.strokeText(text, 128, 36);
  ctx.fillStyle = '#172033';
  ctx.fillText(text, 128, 36);
  const tex = new THREE.CanvasTexture(cv);
  tex.encoding = THREE.sRGBEncoding;
  return tex;
}

function disposeObj(o) {
  o.traverse((x) => {
    if (x.geometry?.dispose) x.geometry.dispose();
    if (x.material?.dispose) x.material.dispose();
  });
}

/**
 * Three.js 3D 지구본 — NASA Blue Marble 텍스처 + 대기 글로우 + 국가 라벨/외곽선,
 * 국가 포커스 시 외곽선 전개와 이슈 핀, 여론 톤 오버레이(등장방형 캔버스 채색).
 * 출처: What in the World.html #globe
 *
 * 렌더링은 three.js가 명령형으로 맡고, React는 컨테이너와 HUD만 그린다.
 * 씬은 마운트 때 한 번 만들고, 이후 prop 변화는 ref에 담긴 API로 전달한다.
 *
 * @param {{countries: object[], texture?: string, iso3?: Record<string, string[]>,
 *          tone?: {name: string, t: Record<string, {s: number, n: number}>}|null,
 *          minSample?: number, focus?: string|null, highlight?: string|null,
 *          pinCities?: Record<string, [number, number][]>,
 *          pinsOf?: (country: object) => {title: string, tr: number}[],
 *          onOpenCountry?: (id: string) => void,
 *          onSelectPin?: (pin: {cid: string, idx: number, title: string}) => void,
 *          showBeacons?: boolean, spinControl?: boolean,
 *          meteorInterval?: number, meteorTopics?: object[],
 *          onMeteorImpact?: (topic: object) => void,
 *          children?: React.ReactNode}} props
 */
export default function GlobeThree({
  countries,
  texture = '/earth.jpg',
  iso3 = { kr: ['KOR'], us: ['USA'], uk: ['GBR'], au: ['AUS'], me: ['ARE', 'QAT'], af: ['ZAF', 'KEN'], br: ['BRA'] },
  tone = null,
  minSample = 30,
  focus = null,
  highlight = null,
  pinCities = {},
  pinsOf,
  onOpenCountry,
  onSelectPin,
  showBeacons = false,
  spinControl = true,
  meteorInterval = 0,
  meteorTopics = [],
  onMeteorImpact,
  children,
}) {
  const wrapRef = useRef(null);
  const apiRef = useRef(null);
  const tipRef = useRef(null);
  const [autoSpin, setAutoSpin] = useState(true);

  /* 콜백은 ref로 넘긴다 — 씬을 다시 만들지 않기 위해 */
  const cb = useRef({});
  cb.current = { onOpenCountry, onSelectPin, onMeteorImpact, pinsOf };

  /* ── 씬 생성 (마운트 1회) ── */
  useEffect(() => {
    const wrap = wrapRef.current;
    const reduced = prefersReducedMotion();

    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    cam.position.set(0, 0, IDLE_CAMERA_Z);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    wrap.appendChild(renderer.domElement);

    const globe = new THREE.Group();
    scene.add(globe);
    globe.rotation.x = 0.16;

    /* 실제 지구 + 조명 + 대기 글로우 */
    const earthTex = new THREE.TextureLoader().load(texture);
    earthTex.encoding = THREE.sRGBEncoding;
    earthTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    /* 흰 바탕에서는 지구가 '검은 공'으로 보이기 쉽다.
       Blue Marble 텍스처의 바다는 원래 짙은 남색이라 조명만 올려서는 한계가 있다.
       그래서 텍스처를 자체발광(emissiveMap)으로도 한 번 더 먹여 바닥 밝기를 깔고,
       방향광은 낮춰 낮/밤의 입체감만 남긴다. */
    globe.add(
      new THREE.Mesh(
        new THREE.SphereGeometry(1, 64, 64),
        new THREE.MeshPhongMaterial({
          map: earthTex,
          emissive: 0xffffff,
          emissiveMap: earthTex,
          emissiveIntensity: 0.62,
          specular: 0x223344,
          shininess: 10,
        }),
      ),
    );
    scene.add(new THREE.AmbientLight(0xc9d4e2, 0.5));
    const sun = new THREE.DirectionalLight(0xfff6e8, 0.62);
    sun.position.set(-2.2, 1.4, 2.6);
    scene.add(sun);
    /* 반대편 채움광 — 밤 반구가 흰 배경 위에서 검게 뭉치지 않도록 */
    const fill = new THREE.DirectionalLight(0xdfe8f5, 0.34);
    fill.position.set(2.5, -1, -2);
    scene.add(fill);
    /* 대기 — 검은 우주에서는 가산 혼합으로 빛나게 했지만, 흰 바탕에서는
       가산 혼합이 곧 흰색이라 아무것도 안 보인다. 일반 혼합으로 바꿔
       구체 둘레에 옅은 파란 테를 두른다. */
    const atmo = new THREE.Mesh(
      new THREE.SphereGeometry(1.11, 48, 48),
      new THREE.ShaderMaterial({
        transparent: true,
        side: THREE.BackSide,
        depthWrite: false,
        vertexShader:
          'varying vec3 vN;void main(){vN=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
        fragmentShader:
          'varying vec3 vN;void main(){float i=pow(.60-dot(vN,vec3(0,0,1.)),3.0);gl_FragColor=vec4(.30,.50,.78,clamp(i,0.,1.)*.42);}',
      }),
    );
    scene.add(atmo);

    /* ── 국가 비콘 / 히트영역 / 링 / 글로우 ── */
    const beacons = [];
    const rings = [];
    const countryLabels = [];
    const countryHoverTargets = [];
    const worldOutlineGroup = new THREE.Group();
    const countryOutlineGroup = new THREE.Group();
    const countryOutlines = new Map();
    globe.add(worldOutlineGroup);
    globe.add(countryOutlineGroup);

    countries.forEach((c) => {
      const pts = [[c.lat, c.lon]];
      if (c.lat2 !== undefined) pts.push([c.lat2, c.lon2]);
      pts.forEach((p, pi) => {
        const v = ll2v(p[0], p[1], 1.015);
        const b = new THREE.Mesh(
          new THREE.SphereGeometry(pi ? 0.016 : 0.022, 12, 12),
          new THREE.MeshBasicMaterial({ color: CYAN }),
        );
        b.position.copy(v);
        b.userData = { id: c.id, name: c.name, flag: c.flag, primary: pi === 0 };
        b.visible = showBeacons;
        globe.add(b);
        beacons.push(b);

        if (pi === 0) {
          const hit = new THREE.Mesh(
            new THREE.SphereGeometry(0.072, 16, 16),
            new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
          );
          hit.position.copy(v);
          hit.userData = { id: c.id, name: c.name, flag: c.flag, type: 'country-hit' };
          globe.add(hit);
          countryHoverTargets.push(hit);
        }

        const ring = new THREE.Mesh(
          new THREE.RingGeometry(0.028, 0.034, 32),
          new THREE.MeshBasicMaterial({
            color: CYAN, transparent: true, opacity: 0.8, side: THREE.DoubleSide,
          }),
        );
        ring.position.copy(v);
        ring.lookAt(v.clone().multiplyScalar(2));
        ring.userData = { t: Math.random() * Math.PI * 2 };
        ring.visible = showBeacons;
        globe.add(ring);
        rings.push(ring);

        const glow = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: glowTex(), color: CYAN, transparent: true, opacity: 0.55,
            depthWrite: false, blending: THREE.AdditiveBlending,
          }),
        );
        glow.scale.setScalar(0.17);
        glow.position.copy(v);
        glow.visible = showBeacons;
        globe.add(glow);
      });
    });

    /* ── 여론 톤 오버레이 구체 (등장방형 캔버스 → CanvasTexture) ── */
    const toneCv = document.createElement('canvas');
    toneCv.width = 2048;
    toneCv.height = 1024;
    const toneCtx = toneCv.getContext('2d');
    const toneTex = new THREE.CanvasTexture(toneCv);
    toneTex.encoding = THREE.sRGBEncoding;
    const toneMesh = new THREE.Mesh(
      new THREE.SphereGeometry(1.004, 64, 64),
      new THREE.MeshBasicMaterial({ map: toneTex, transparent: true, depthWrite: false, opacity: 0.92 }),
    );
    toneMesh.visible = false;
    globe.add(toneMesh);

    const TONE = { active: false, topic: null, minN: minSample };
    let GEO = null;
    let geoTried = false;

    const toneColorOf = (id) => {
      const d = TONE.topic && TONE.topic.t[id];
      if (!d) return null;
      return d.s == null || (d.n != null && TONE.minN != null && d.n < TONE.minN) ? NO_SAMPLE : toneRGB(d.s);
    };
    const beaconBaseColor = (id) => {
      if (TONE.active) {
        const c = toneColorOf(id);
        if (c) return rgbHex(c);
      }
      return CYAN;
    };
    const syncBeacons = (focusedId) => {
      beacons.forEach((b) =>
        b.material.color.set(b.userData.id === focusedId ? AMBER : beaconBaseColor(b.userData.id)),
      );
    };

    /* 등장방형 좌표 변환 + 폴리곤 채색 (안티메리디안 링 보정 포함) */
    const TX = (lon) => ((lon + 180) / 360) * toneCv.width;
    const TY = (lat) => ((90 - lat) / 180) * toneCv.height;
    const traceRing = (ring, shift) => {
      ring.forEach((p, i) => {
        const x = TX(p[0] + shift);
        const y = TY(p[1]);
        if (i) toneCtx.lineTo(x, y);
        else toneCtx.moveTo(x, y);
      });
      toneCtx.closePath();
    };
    /* 링 전체를 한 패스로 그려 내부 홀(예: 레소토)을 보존한다 */
    const paintPoly = (rings2) => {
      toneCtx.beginPath();
      rings2.forEach((ring) => {
        let mn = 180;
        let mx = -180;
        ring.forEach((p) => {
          if (p[0] < mn) mn = p[0];
          if (p[0] > mx) mx = p[0];
        });
        if (mx - mn > 180) {
          /* 경도 180선을 넘는 링: 음수 경도 +360 후 두 위치에 이어 그린다 */
          const r = ring.map((p) => [p[0] < 0 ? p[0] + 360 : p[0], p[1]]);
          traceRing(r, 0);
          traceRing(r, -360);
        } else traceRing(ring, 0);
      });
      toneCtx.fill('evenodd');
      toneCtx.stroke();
    };
    const paintTone = () => {
      toneCtx.clearRect(0, 0, toneCv.width, toneCv.height);
      if (TONE.active) {
        countries.forEach((c) => {
          const col = toneColorOf(c.id);
          if (!col) return;
          toneCtx.fillStyle = `rgba(${col},.55)`;
          toneCtx.strokeStyle = `rgba(${col},.95)`;
          toneCtx.lineWidth = 2;
          toneCtx.shadowColor = `rgba(${col},.9)`;
          toneCtx.shadowBlur = 14;
          const feats = GEO && GEO[c.id];
          if (feats && feats.length) {
            feats.forEach((g) => {
              if (g.type === 'Polygon') paintPoly(g.coordinates);
              else if (g.type === 'MultiPolygon') g.coordinates.forEach(paintPoly);
            });
          } else {
            /* GeoJSON 로딩 전/실패 시: 소프트 원형 폴백 */
            const pts = [[c.lat, c.lon]];
            if (c.lat2 !== undefined) pts.push([c.lat2, c.lon2]);
            pts.forEach((p) => {
              const x = TX(p[1]);
              const y = TY(p[0]);
              const r = 46;
              const g = toneCtx.createRadialGradient(x, y, 4, x, y, r);
              g.addColorStop(0, `rgba(${col},.7)`);
              g.addColorStop(1, `rgba(${col},0)`);
              toneCtx.save();
              toneCtx.shadowBlur = 0;
              toneCtx.fillStyle = g;
              toneCtx.beginPath();
              toneCtx.arc(x, y, r, 0, 7);
              toneCtx.fill();
              toneCtx.restore();
            });
          }
        });
        toneCtx.shadowBlur = 0;
      }
      toneTex.needsUpdate = true;
    };

    /* ── 국가 외곽선 · 라벨 ── */
    const countryRings = (c) => {
      const out = [];
      const feats = GEO && GEO[c.id];
      if (feats && feats.length) {
        const rs = [];
        feats.forEach((g) => {
          if (g.type === 'Polygon') rs.push(g.coordinates[0]);
          else if (g.type === 'MultiPolygon') g.coordinates.forEach((p) => rs.push(p[0]));
        });
        rs.sort((a, b) => b.length - a.length);
        rs.slice(0, 6).forEach((r) => {
          const step = Math.max(1, Math.floor(r.length / 110));
          const pts = [];
          for (let i = 0; i < r.length; i += step) pts.push(r[i]);
          pts.push(r[0]);
          if (pts.length > 7) out.push(pts);
        });
      }
      if (!out.length) {
        /* GeoJSON 미로딩: 국가 크기 근사 원 */
        const R = FALLBACK_RAD[c.id] || 4;
        const pts = [];
        for (let i = 0; i <= 64; i++) {
          const a = (i / 64) * Math.PI * 2;
          pts.push([
            c.lon + (R * Math.cos(a)) / Math.cos((c.lat * Math.PI) / 180),
            c.lat + R * Math.sin(a),
          ]);
        }
        out.push(pts);
      }
      return out; /* [lon,lat] 링 배열 */
    };

    const buildCountryLabels = () => {
      if (countryLabels.length) return;
      countries.forEach((c) => {
        const label = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: labelTex(c.name), transparent: true, depthTest: true, depthWrite: false,
          }),
        );
        label.position.copy(ll2v(c.lat, c.lon, 1.115));
        label.scale.set(0.16, 0.046, 1);
        label.userData = { id: c.id, name: c.name, flag: c.flag, type: 'country-label' };
        globe.add(label);
        countryLabels.push(label);
      });
    };

    const buildCountryOutlines = () => {
      countryOutlineGroup.clear();
      countryOutlines.clear();
      countries.forEach((c) => {
        const lines = [];
        countryRings(c).forEach((ring) => {
          const pts = ring.map((p) => ll2v(p[1], p[0], 1.008));
          const line = new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(pts),
            new THREE.LineBasicMaterial({ color: 0x89ddff, transparent: true, opacity: 0.2, depthTest: true }),
          );
          line.userData = { id: c.id, name: c.name, flag: c.flag, type: 'country-outline' };
          countryOutlineGroup.add(line);
          lines.push(line);
        });
        countryOutlines.set(c.id, lines);
      });
    };

    const buildWorldOutlines = (features) => {
      if (!features || worldOutlineGroup.children.length) return;
      features.forEach((f) => {
        const rs = [];
        if (f.geometry.type === 'Polygon') rs.push(f.geometry.coordinates[0]);
        else if (f.geometry.type === 'MultiPolygon') f.geometry.coordinates.forEach((p) => rs.push(p[0]));
        rs.forEach((ring) => {
          const step = Math.max(1, Math.floor(ring.length / 90));
          const pts = [];
          for (let i = 0; i < ring.length; i += step) pts.push(ll2v(ring[i][1], ring[i][0], 1.003));
          pts.push(ll2v(ring[0][1], ring[0][0], 1.003));
          worldOutlineGroup.add(
            new THREE.Line(
              new THREE.BufferGeometry().setFromPoints(pts),
              new THREE.LineBasicMaterial({ color: 0xb8dfff, transparent: true, opacity: 0.16, depthTest: true }),
            ),
          );
        });
      });
    };

    const setCountryOutlineActive = (id) => {
      countryOutlines.forEach((lines, cid) => {
        lines.forEach((line) => {
          const on = id && cid === id;
          line.material.color.set(on ? AMBER : 0x89ddff);
          line.material.opacity = on ? 1 : 0.2;
          line.scale.setScalar(on ? 1.035 : 1);
        });
      });
      countryLabels.forEach((label) => {
        const on = id && label.userData.id === id;
        label.scale.set(on ? 0.17 : 0.16, on ? 0.05 : 0.046, 1);
        label.material.opacity = on ? 1 : 0.82;
      });
    };

    const loadGeo = () => {
      if (geoTried) return;
      geoTried = true;
      fetch(GEO_URL)
        .then((r) => r.json())
        .then((gj) => {
          GEO = {};
          buildWorldOutlines(gj.features);
          gj.features.forEach((f) => {
            const iso = f.properties.ISO_A3 !== '-99' ? f.properties.ISO_A3 : f.properties.ADM0_A3;
            Object.keys(iso3).forEach((id) => {
              if (iso3[id].includes(iso)) {
                GEO[id] = GEO[id] || [];
                GEO[id].push(f.geometry);
              }
            });
          });
          buildCountryOutlines();
          if (TONE.active) paintTone();
        })
        .catch(() => {
          /* 폴백(근사 원)으로 계속 표시한다 */
        });
    };

    /* ── 국가 포커스 FX: 중심에서 외곽선으로 전개 + 이슈 핀 ── */
    const pinHeads = [];
    let FX = null;

    const clearCountryFx = () => {
      if (!FX) return;
      disposeObj(FX.group);
      globe.remove(FX.group);
      pinHeads.length = 0;
      FX = null;
    };

    const spawnCountryFx = (c) => {
      clearCountryFx();
      const g = new THREE.Group();
      globe.add(g);
      const lines = countryRings(c).map((pts) => {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pts.length * 3), 3));
        const line = new THREE.Line(
          geo,
          new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0 }),
        );
        line.userData.pts = pts;
        g.add(line);
        return line;
      });
      const cities = pinCities[c.id] || [[c.lat, c.lon]];
      const arts = cb.current.pinsOf ? cb.current.pinsOf(c) : [];
      const pins = arts.map((a, i) => {
        const city = cities[i % cities.length];
        const col = a.tr >= 75 ? 0x57e6a8 : a.tr >= 50 ? AMBER : 0xff6b7a;
        const pin = new THREE.Group();
        const stem = new THREE.Mesh(
          new THREE.CylinderGeometry(0.0022, 0.0022, 0.05, 6),
          new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.9 }),
        );
        stem.position.y = 0.025;
        const head = new THREE.Mesh(
          new THREE.SphereGeometry(0.015, 10, 10),
          new THREE.MeshBasicMaterial({ color: col }),
        );
        head.position.y = 0.055;
        head.userData = { type: 'pin', cid: c.id, idx: i, title: a.title, tr: a.tr };
        pin.add(stem);
        pin.add(head);
        pin.visible = false;
        g.add(pin);
        pinHeads.push(head);
        return { pin, city, delay: 220 + i * 110 };
      });
      FX = { group: g, lines, pins, c, born: performance.now(), dur: reduced ? 1 : 950 };
    };

    const _up = new THREE.Vector3(0, 1, 0);
    const _nv = new THREE.Vector3();
    const _qv = new THREE.Quaternion();
    const fxTick = (t) => {
      if (!FX) return;
      const now = performance.now();
      const c = FX.c;
      const u = Math.min(1, (now - FX.born) / FX.dur);
      const e = 1 - (1 - u) ** 3;
      /* 중심점에서 국가 외곽선으로 펼쳐지는 모핑 */
      FX.lines.forEach((line) => {
        const pts = line.userData.pts;
        const arr = line.geometry.attributes.position.array;
        pts.forEach((p, i) => {
          const la = c.lat + (p[1] - c.lat) * e;
          const lo = c.lon + (shortLon(c.lon, p[0]) - c.lon) * e;
          const v = ll2v(la, lo, 1.008);
          arr[i * 3] = v.x;
          arr[i * 3 + 1] = v.y;
          arr[i * 3 + 2] = v.z;
        });
        line.geometry.attributes.position.needsUpdate = true;
        line.material.opacity = 0.85 * e;
      });
      /* 핀: 중심에서 도시 위치로 시차를 두고 전개 */
      FX.pins.forEach((pn) => {
        const pu = Math.min(1, Math.max(0, (now - FX.born - pn.delay) / 600));
        if (pu <= 0) {
          pn.pin.visible = false;
          return;
        }
        pn.pin.visible = true;
        const pe = 1 - (1 - pu) ** 3;
        const la = c.lat + (pn.city[0] - c.lat) * pe;
        const lo = c.lon + (shortLon(c.lon, pn.city[1]) - c.lon) * pe;
        const v = ll2v(la, lo, 1.0);
        pn.pin.position.copy(v);
        _nv.copy(v).normalize();
        _qv.setFromUnitVectors(_up, _nv);
        pn.pin.quaternion.copy(_qv);
        pn.pin.scale.setScalar(pu >= 1 ? 1 + 0.14 * Math.sin(t * 3 + pn.delay) : pe);
      });
    };

    /* ── 신규 토픽 별똥별 ── */
    const meteors = [];
    const impacts = [];
    const spawnMeteor = (tp) => {
      const c = countries.find((x) => x.id === tp.c);
      if (!c) return;
      const end = ll2v(c.lat, c.lon, 1.012);
      const n = end.clone().normalize();
      const start = n
        .clone()
        .multiplyScalar(3.4)
        .add(new THREE.Vector3((Math.random() - 0.5) * 2.2, 1.2 + Math.random() * 0.8, (Math.random() - 0.5) * 2.2));
      const mid = start.clone().lerp(end, 0.55).add(n.clone().multiplyScalar(0.5));
      const curve = new THREE.QuadraticBezierCurve3(start, mid, end);
      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.02, 10, 10),
        new THREE.MeshBasicMaterial({ color: 0xfff6e0 }),
      );
      const glow = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: glowTex(), color: 0xffc76b, transparent: true, opacity: 0.9,
          depthWrite: false, blending: THREE.AdditiveBlending,
        }),
      );
      glow.scale.setScalar(0.3);
      head.add(glow);
      const trail = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([start, start]),
        new THREE.LineBasicMaterial({ color: 0xffd9a0, transparent: true, opacity: 0.85 }),
      );
      globe.add(head);
      globe.add(trail);
      meteors.push({ head, trail, curve, born: performance.now(), dur: 1700, tp, c, pts: [] });
    };

    const meteorImpact = (m) => {
      const v = ll2v(m.c.lat, m.c.lon, 1.016);
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.02, 0.027, 32),
        new THREE.MeshBasicMaterial({ color: 0xffc76b, transparent: true, opacity: 0.9, side: THREE.DoubleSide }),
      );
      ring.position.copy(v);
      ring.lookAt(v.clone().multiplyScalar(2));
      globe.add(ring);
      impacts.push({ ring, born: performance.now() });
      cb.current.onMeteorImpact?.(m.tp);
    };

    const meteorTick = () => {
      const now = performance.now();
      for (let i = meteors.length - 1; i >= 0; i--) {
        const m = meteors[i];
        const u = (now - m.born) / m.dur;
        if (u >= 1) {
          meteorImpact(m);
          disposeObj(m.head);
          disposeObj(m.trail);
          globe.remove(m.head);
          globe.remove(m.trail);
          meteors.splice(i, 1);
          continue;
        }
        const e = u * u; /* 가속 낙하 */
        m.curve.getPoint(e, m.head.position);
        m.pts.unshift(m.head.position.clone());
        if (m.pts.length > 22) m.pts.pop();
        m.trail.geometry.setFromPoints(m.pts);
        m.trail.material.opacity = 0.85 * (1 - e * 0.4);
      }
      for (let i = impacts.length - 1; i >= 0; i--) {
        const im = impacts[i];
        const u = (now - im.born) / 900;
        if (u >= 1) {
          disposeObj(im.ring);
          globe.remove(im.ring);
          impacts.splice(i, 1);
          continue;
        }
        im.ring.scale.setScalar(1 + u * 4.5);
        im.ring.material.opacity = 0.9 * (1 - u);
      }
    };

    /* ── 인터랙션 ── */
    const ray = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let dragging = false;
    let px = 0;
    let py = 0;
    let dragDistance = 0;
    let vx = 0;
    let vy = 0;
    let spin = true;
    let focusRotation = null;
    let targetZ = IDLE_CAMERA_Z;
    let focusedId = null;
    let highlightId = null; /* 목록만 좁힌 상태(줌 없이 윤곽만 강조) */
    const activeId = () => focusedId || highlightId;
    const focusCameraZ = () => {
      const verticalHalfFov = THREE.MathUtils.degToRad(cam.fov / 2);
      const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * cam.aspect);
      const limitingHalfFov = Math.min(verticalHalfFov, horizontalHalfFov);
      return VISIBLE_GLOBE_RADIUS / Math.sin(limitingHalfFov * FOCUS_FILL_RATIO);
    };

    const hitTargets = () =>
      beacons.filter((b) => b.visible).concat(pinHeads, countryLabels, countryHoverTargets);

    const onDown = (e) => {
      dragging = true;
      vx = 0;
      vy = 0;
      px = e.clientX;
      py = e.clientY;
      dragDistance = 0;
      wrap.classList.add(s.dragging);
      spin = false;
      setAutoSpin(false);
      focusRotation = null;
    };
    const onUp = () => {
      dragging = false;
      wrap.classList.remove(s.dragging);
    };
    const onMove = (e) => {
      if (dragging) {
        const dx = e.clientX - px;
        const dy = e.clientY - py;
        dragDistance += Math.hypot(dx, dy);
        vx = dx * 0.0045;
        vy = dy * 0.0045;
        globe.rotation.y += vx;
        globe.rotation.x = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, globe.rotation.x + vy));
        px = e.clientX;
        py = e.clientY;
      }
      const r = wrap.getBoundingClientRect();
      mouse.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      mouse.y = -((e.clientY - r.top) / r.height) * 2 + 1;
      ray.setFromCamera(mouse, cam);
      const hit = ray.intersectObjects(hitTargets())[0];
      const tip = tipRef.current;
      if (hit && e.target === renderer.domElement) {
        tip.classList.add(s.show);
        tip.style.left = `${e.clientX - r.left}px`;
        tip.style.top = `${e.clientY - r.top}px`;
        const u = hit.object.userData;
        setCountryOutlineActive(u.cid || u.id);
        let tt;
        if (u.type === 'pin') {
          tt = `📌 <b>${escapeHtml(u.title)}</b><br>클릭하면 기사로 이동`;
        } else {
          tt = `${escapeHtml(u.flag)} <b>${escapeHtml(u.name)}</b> · 클릭하면 국가 분석으로 이동`;
          if (TONE.active && TONE.topic.t[u.id]) {
            const d = TONE.topic.t[u.id];
            const badge = d.s == null ? '분석 없음' : d.n != null && TONE.minN != null && d.n < TONE.minN ? '표본부족' : (d.s > 0 ? '+' : '') + d.s.toFixed(2);
            tt += `<br>「${escapeHtml(TONE.topic.name)}」 톤 ${badge}${d.n == null ? ' · 표본 수 미제공' : ` · ${d.n}건`}`;
          }
        }
        tip.innerHTML = tt;
        wrap.classList.add(s.pointing);
      } else {
        tip.classList.remove(s.show);
        setCountryOutlineActive(activeId());
        wrap.classList.remove(s.pointing);
      }
    };
    const onClick = () => {
      if (dragDistance >= 5) {
        dragDistance = 0;
        vx = 0;
        vy = 0;
        return;
      }
      ray.setFromCamera(mouse, cam);
      const hit = ray.intersectObjects(hitTargets())[0];
      if (!hit) return;
      const u = hit.object.userData;
      if (u.type === 'pin') {
        cb.current.onSelectPin?.(u);
        return;
      }
      cb.current.onOpenCountry?.(u.id);
    };

    wrap.addEventListener('pointerdown', onDown);
    addEventListener('pointerup', onUp);
    addEventListener('pointermove', onMove);
    wrap.addEventListener('click', onClick);

    /* ── 루프 ── */
    const resize = () => {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
      if (focusedId) targetZ = focusCameraZ();
    };
    addEventListener('resize', resize);
    resize();

    let t = 0;
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      t += 0.016;
      if (spin && !reduced) globe.rotation.y += 0.0016;
      if (focusRotation) {
        globe.rotation.x += (focusRotation.pitch - globe.rotation.x) * 0.06;
        globe.rotation.y += (focusRotation.yaw - globe.rotation.y) * 0.06;
        globe.rotation.z += (0 - globe.rotation.z) * 0.06;
        if (
          Math.abs(focusRotation.pitch - globe.rotation.x) < 0.005
          && Math.abs(focusRotation.yaw - globe.rotation.y) < 0.005
        ) {
          globe.rotation.set(focusRotation.pitch, focusRotation.yaw, 0);
          focusRotation = null;
        }
      }
      cam.position.z += (targetZ - cam.position.z) * 0.06;
      if (!reduced) {
        rings.forEach((r) => {
          const sc = 1 + 0.55 * (Math.sin(t * 2.2 + r.userData.t) * 0.5 + 0.5);
          r.scale.setScalar(sc);
          r.material.opacity = 0.85 - (sc - 1) * 1.1;
        });
        meteorTick();
      }
      fxTick(t);
      renderer.render(scene, cam);
    };
    loop();

    buildCountryLabels();
    buildCountryOutlines();
    loadGeo(); /* 국가 외곽선 전개·여론 톤 채색에 공용 */

    /* ── 바깥에서 쓰는 명령형 API ── */
    apiRef.current = {
      setTone(topic, minN) {
        TONE.minN = minN;
        if (!topic) {
          TONE.active = false;
          TONE.topic = null;
          toneMesh.visible = false;
        } else {
          TONE.active = true;
          TONE.topic = topic;
          loadGeo();
          toneMesh.visible = true;
        }
        paintTone();
        syncBeacons(focusedId);
      },
      focusCountry(id) {
        const c = countries.find((x) => x.id === id);
        if (!c) return;
        focusedId = id;
        clearCountryFx();
        /* 나라를 정면에 세우되 북쪽은 위로 — 세계지도와 같은 자세다 */
        const target = orientTo(c.lat, c.lon);
        focusRotation = {
          pitch: target.pitch,
          yaw: globe.rotation.y + shortestAngle(globe.rotation.y, target.yaw),
        };
        /* 화면의 짧은 축 안에 지구본 외곽이 남는 범위까지만 확대한다. */
        targetZ = focusCameraZ();
        spin = false;
        setAutoSpin(false);
        syncBeacons(id);
        setCountryOutlineActive(id);
        spawnCountryFx(c);
      },
      reset() {
        focusedId = null;
        focusRotation = null;
        targetZ = IDLE_CAMERA_Z;
        spin = true;
        setAutoSpin(true);
        clearCountryFx();
        setCountryOutlineActive(highlightId);
        syncBeacons(highlightId);
      },
      /* 줌·핀 없이 윤곽만 강조한다 — 목록을 좁혔을 뿐 화면을 옮긴 게 아니므로 */
      setHighlight(id) {
        highlightId = id || null;
        setCountryOutlineActive(activeId());
        syncBeacons(activeId());
      },
      setSpin(on) {
        spin = !!on;
        focusRotation = null;
        setAutoSpin(!!on);
      },
      spawnMeteor,
    };

    return () => {
      cancelAnimationFrame(raf);
      removeEventListener('resize', resize);
      removeEventListener('pointerup', onUp);
      removeEventListener('pointermove', onMove);
      wrap.removeEventListener('pointerdown', onDown);
      wrap.removeEventListener('click', onClick);
      clearCountryFx();
      disposeObj(scene);
      renderer.dispose();
      if (renderer.domElement.parentNode === wrap) wrap.removeChild(renderer.domElement);
      apiRef.current = null;
    };
    /* 씬은 한 번만 만든다. 이후 변화는 아래 effect들이 API로 전달한다. */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* prop → 씬 반영 */
  useEffect(() => {
    apiRef.current?.setTone(tone, minSample);
  }, [tone, minSample]);

  useEffect(() => {
    if (focus) apiRef.current?.focusCountry(focus);
    else apiRef.current?.reset();
  }, [focus]);

  useEffect(() => {
    apiRef.current?.setHighlight(highlight);
  }, [highlight]);

  /* 별똥별 — meteorInterval(ms)이 0보다 크면 순서대로 떨어뜨린다 */
  useEffect(() => {
    if (!meteorInterval || !meteorTopics.length) return undefined;
    let i = 0;
    const id = setInterval(() => {
      apiRef.current?.spawnMeteor(meteorTopics[i++ % meteorTopics.length]);
    }, meteorInterval);
    return () => clearInterval(id);
  }, [meteorInterval, meteorTopics]);

  return (
    <div className={s.wrap}>
      <div
        ref={wrapRef}
        className={s.canvas}
        role="application"
        aria-label="분석 대상 국가가 표시된 3D 지구본. 국가를 클릭하면 해당 국가 기사로 이동합니다."
      />
      <div className={s.tip} ref={tipRef} />
      {children}
      {spinControl && (
        <div className={s.spin} aria-label="지구 자전 제어">
          <button
            type="button"
            className={`${s.spinBtn} ${autoSpin ? s.on : ''}`}
            title={autoSpin ? '지구 자전 멈춤' : '지구 자전 재생'}
            aria-label={autoSpin ? '지구 자전 멈춤' : '지구 자전 재생'}
            onClick={() => apiRef.current?.setSpin(!autoSpin)}
          >
            {autoSpin ? 'Ⅱ' : '▶'}
          </button>
        </div>
      )}
    </div>
  );
}

/** 지구본 좌측 상단 HUD — GlobeThree의 children으로 넣는다 */
export function GlobeHud({ kicker = 'Orbital View', title, desc }) {
  return (
    <div className={s.hud}>
      {kicker && <div className={s.kicker}>{kicker}</div>}
      {title && <h2>{title}</h2>}
      {desc && <p>{desc}</p>}
    </div>
  );
}
