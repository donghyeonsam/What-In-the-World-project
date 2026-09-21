import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { toneLabel3, toneRGB, NO_SAMPLE, rgbHex } from '../../lib/tone.js';
import { shortLon, prefersReducedMotion } from '../../lib/format.js';
import { countryCameraZ } from '../../lib/globeFocus.js';
import { advanceGlobeInertia, globeReleaseVelocity } from '../../lib/globeInertia.js';
import { earthTextureUrls, loadEarthTexture } from '../../lib/earthTextures.js';
import { createMentionGroup, updateMentionFlow } from '../../lib/mentionLinks.js';
import { layoutGlobeCallout, resolveGlobeCalloutSide } from '../../lib/globeCallout.js';
import s from './GlobeThree.module.css';
import { flagOf, scoreOf } from '../../data/responseAdapters.js';
import { displayCountryCode } from '../../data/countries.js';
import SatelliteRelay from './SatelliteRelay.jsx';
import { issueCardSlots, placeIssueCards } from '../../lib/issueCardLayout.js';

const GEO_URL =
  'https://raw.githubusercontent.com/vasturiano/globe.gl/master/example/datasets/ne_110m_admin_0_countries.geojson';

/* GeoJSON이 아직 없을 때 국가 외곽선 대신 그리는 근사 원의 반지름(도) */
const FALLBACK_RAD = { kr: 2.6, us: 12, uk: 4, au: 14, me: 3.2, af: 7, br: 13 };

const CYAN = 0x6fe7ff;
const AMBER = 0xffb454;
const IDLE_CAMERA_Z = 3.7;
const GLOBAL_ISSUE_CAMERA_SCALE = 1.1;
const MIN_CAMERA_Z = 1.5;
const WHEEL_ZOOM_SPEED = 0.0015;
const CAMERA_LERP = 0.06;
// 같은 거리의 국가 이동·자동 확대가 기존보다 약 1.2배 빠르게 수렴한다.
const COUNTRY_FOCUS_LERP = 1 - (1 - CAMERA_LERP) ** 1.2;
const FOCUS_FILL_RATIO = 0.88;
const VISIBLE_GLOBE_RADIUS = 1.04;
const NO_MENTION_RELATIONS = [];
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
  cv.width = 512;
  cv.height = 144;
  ctx.scale(2, 2);
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
 *          onGlobeMove?: () => void,
 *          countryClickHint?: string,
 *          onSelectPin?: (pin: {cid: string, idx: number, title: string}) => void,
 *          showBeacons?: boolean, spinControl?: boolean,
 *          meteorInterval?: number, meteorTopics?: object[],
 *          onMeteorImpact?: (topic: object) => void,
 *          children?: React.ReactNode}} props
 */
export default function GlobeThree({
  countries,
  timeTravel = null,
  timeTravelDirection = -1,
  timeMachineActive = false,
  texture,
  iso3 = { kr: ['KOR'], us: ['USA'], uk: ['GBR'], au: ['AUS'], me: ['ARE', 'QAT'], af: ['ZAF', 'KEN'], br: ['BRA'] },
  tone = null,
  minSample = 30,
  focus = null,
  highlight = null,
  mentionRelations = NO_MENTION_RELATIONS,
  pinCities = {},
  pinsOf,
  onOpenCountry,
  onGlobeMove,
  countryClickHint = '클릭하면 국가 분석으로 이동',
  onSelectPin,
  showBeacons = false,
  spinControl = true,
  meteorInterval = 0,
  meteorTopics = [],
  onMeteorImpact,
  issueCards = [],
  selectedIssueCountry = null,
  onSelectIssueCountry,
  satelliteDemo = false,
  globalIssueView = false,
  calloutCountry = null,
  calloutToneColor = '154, 143, 196',
  callout = null,
  children,
}) {
  const issueCardRefs = useRef(new Map());
  const globalIssueRef = useRef(globalIssueView);
  globalIssueRef.current = globalIssueView;
  const satelliteRef = useRef(null);
  const signalRefs = useRef([]);
  const satelliteDemoRef = useRef(satelliteDemo);
  satelliteDemoRef.current = satelliteDemo;
  const issueCardsRef = useRef([]);
  issueCardsRef.current = issueCards;
  const selectedIssueCountryRef = useRef(selectedIssueCountry);
  selectedIssueCountryRef.current = selectedIssueCountry;
  const hoveredIssueCardRef = useRef(null);
  const travelRef = useRef(timeTravel);
  travelRef.current = timeTravel;
  const travelDirectionRef = useRef(timeTravelDirection);
  travelDirectionRef.current = timeTravelDirection;
  const timeMachineRef = useRef(timeMachineActive);
  timeMachineRef.current = timeMachineActive;
  const wrapRef = useRef(null);
  const apiRef = useRef(null);
  const tipRef = useRef(null);
  const calloutRef = useRef(null);
  const calloutLineRef = useRef(null);
  const calloutAnchorRef = useRef(null);
  const calloutSizeRef = useRef({ width: 0, height: 0 });
  const calloutCountryRef = useRef(calloutCountry);
  const userClearedFocusRef = useRef(false);
  calloutCountryRef.current = calloutCountry;
  const [autoSpin, setAutoSpin] = useState(() => !prefersReducedMotion());
  const [earthStatus, setEarthStatus] = useState('loading');

  /* 콜백은 ref로 넘긴다 — 씬을 다시 만들지 않기 위해 */
  const cb = useRef({});
  cb.current = { onOpenCountry, onGlobeMove, onSelectPin, onMeteorImpact, pinsOf, countryClickHint };

  /* ── 씬 생성 (마운트 1회) ── */
  useEffect(() => {
    const wrap = wrapRef.current;
    const reduced = prefersReducedMotion();
    let textureReady = false;
    let firstFrameRendered = false;
    setEarthStatus('loading');

    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    cam.position.set(0, 0, IDLE_CAMERA_Z);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    // 일반 DPI 화면도 슈퍼샘플링하되 고밀도 화면에서는 GPU 부하를 제한한다.
    renderer.setPixelRatio(Math.min(Math.max(window.devicePixelRatio || 1, 1.5), 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    wrap.appendChild(renderer.domElement);

    const globe = new THREE.Group();
    scene.add(globe);
    // 초기 화면만 일본 부근을 향하게 한다. 이후 자전·드래그·국가 포커스는 그대로 유지한다.
    const initialOrientation = orientTo(35, 138);
    globe.rotation.set(initialOrientation.pitch, initialOrientation.yaw, 0);
    let mentionGroup = new THREE.Group();
    globe.add(mentionGroup);

    /* 실제 지구 + 조명 + 대기 글로우 */
    const textureUrls = earthTextureUrls({
      maxTextureSize: renderer.capabilities.maxTextureSize,
      deviceMemory: navigator.deviceMemory,
      hardwareConcurrency: navigator.hardwareConcurrency,
      coarsePointer: window.matchMedia?.('(pointer: coarse)').matches ?? true,
      saveData: navigator.connection?.saveData,
      customTexture: texture,
    });
    /* 흰 바탕에서는 지구가 '검은 공'으로 보이기 쉽다.
       Blue Marble 텍스처의 바다는 원래 짙은 남색이라 조명만 올려서는 한계가 있다.
       그래서 텍스처를 자체발광(emissiveMap)으로도 한 번 더 먹여 바닥 밝기를 깔고,
       방향광은 낮춰 낮/밤의 입체감만 남긴다. */
    const earthMaterial = new THREE.MeshPhongMaterial({
      emissive: 0x000000,
      emissiveIntensity: 0.62,
      specular: 0x223344,
      shininess: 10,
    });
    let disposeEarthTexture = () => {};
    const startEarthLoad = () => {
      disposeEarthTexture();
      textureReady = false;
      firstFrameRendered = false;
      setEarthStatus('loading');
      disposeEarthTexture = loadEarthTexture(new THREE.TextureLoader(), textureUrls, {
      onLoad(earthTex, url) {
        earthTex.encoding = THREE.sRGBEncoding;
        earthTex.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
        // 표면과 자체발광에 같은 GPU 텍스처를 공유한다.
        earthMaterial.map = earthTex;
        earthMaterial.emissiveMap = earthTex;
        earthMaterial.emissive.set(0xffffff);
        earthMaterial.needsUpdate = true;
        wrap.dataset.earthTexture = url;
        textureReady = true;
      },
      onError(error) {
        console.warn('지구 표면 텍스처를 불러오지 못했습니다.', error);
        setEarthStatus('error');
      },
      });
    };
    startEarthLoad();
    globe.add(new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96), earthMaterial));
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
      new THREE.SphereGeometry(1.045, 48, 48),
      new THREE.ShaderMaterial({
        transparent: true,
        side: THREE.BackSide,
        depthWrite: false,
        vertexShader:
          'varying vec3 vN;void main(){vN=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
        fragmentShader:
          'varying vec3 vN;void main(){float i=pow(max(.60-dot(vN,vec3(0,0,1.)),0.),3.0);gl_FragColor=vec4(.30,.50,.78,clamp(i,0.,1.)*.16);}',
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
      const selectedGeometry = !TONE.active && focusedId ? GEO?.[focusedId] : null;
      toneMesh.visible = TONE.active || Boolean(selectedGeometry?.length);
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
      } else if (selectedGeometry?.length) {
        // 선택 국가는 지형이 보이는 얇은 채움으로 표시한다. 논조 색과는 겹치지 않는다.
        toneCtx.fillStyle = 'rgba(255,180,84,.18)';
        toneCtx.strokeStyle = 'rgba(255,215,151,.98)';
        toneCtx.lineWidth = 2.5;
        toneCtx.shadowBlur = 0;
        selectedGeometry.forEach((geometry) => {
          if (geometry.type === 'Polygon') paintPoly(geometry.coordinates);
          else if (geometry.type === 'MultiPolygon') geometry.coordinates.forEach(paintPoly);
        });
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

    const ringContains = (ring, lon, lat) => {
      const points = [];
      for (const [x, y] of ring) {
        const previous = points.length ? points[points.length - 1][0] : lon;
        points.push([previous + ((x - previous + 540) % 360) - 180, y]);
      }
      let inside = false;
      for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
        const [ax, ay] = points[i];
        const [bx, by] = points[j];
        if ((ay > lat) !== (by > lat) && lon < ((bx - ax) * (lat - ay)) / (by - ay) + ax) inside = !inside;
      }
      return inside;
    };

    const countryAtSurface = () => {
      if (!GEO) return null;
      const center = globe.getWorldPosition(new THREE.Vector3());
      const surface = ray.ray.intersectSphere(new THREE.Sphere(center, 1), new THREE.Vector3());
      if (!surface) return null;
      const local = globe.worldToLocal(surface.clone()).normalize();
      const lat = THREE.MathUtils.radToDeg(Math.asin(Math.max(-1, Math.min(1, local.y))));
      const lon = ((THREE.MathUtils.radToDeg(Math.atan2(local.z, -local.x)) - 180 + 540) % 360) - 180;
      const id = Object.keys(GEO).find((code) => GEO[code].some((geometry) => {
        const polygons = geometry.type === 'Polygon' ? [geometry.coordinates]
          : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
        return polygons.some(([outer, ...holes]) => ringContains(outer, lon, lat)
          && !holes.some((hole) => ringContains(hole, lon, lat)));
      }));
      return id ? { id } : null;
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
      disposeObj(countryOutlineGroup);
      countryOutlineGroup.clear();
      countryOutlines.clear();
      countries.forEach((c) => {
        const lines = [];
        // 윤곽선은 줌 계산용 단순화 좌표 대신 실제 국경 좌표를 사용한다.
        const rings = GEO?.[c.id]?.flatMap((geometry) => geometry.type === 'Polygon'
          ? geometry.coordinates : geometry.coordinates.flat()) || countryRings(c);
        rings.forEach((ring) => {
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
          const selected = cid === focusedId;
          const hovered = id && cid === id;
          line.material.color.set(selected ? 0xffd797 : hovered ? AMBER : 0x89ddff);
          line.material.opacity = selected || hovered ? 1 : 0.2;
          // 국경을 구체 밖으로 부풀리면 해안선과 어긋나므로 표면에 고정한다.
          line.scale.setScalar(1);
        });
      });
      countryLabels.forEach((label) => {
        const selected = label.userData.id === focusedId;
        const hovered = id && label.userData.id === id;
        label.scale.set(selected ? 0.195 : hovered ? 0.17 : 0.16, selected ? 0.056 : hovered ? 0.05 : 0.046, 1);
        label.material.color.set(selected && !TONE.active ? 0xffd797 : 0xffffff);
        label.material.opacity = selected || hovered ? 1 : 0.82;
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
            const rawIso2 = f.properties.ISO_A2 !== '-99' ? f.properties.ISO_A2 : f.properties.WB_A2;
            const iso2 = displayCountryCode(rawIso2).toLowerCase();
            if (/^[a-z]{2}$/.test(iso2)) {
              GEO[iso2] = GEO[iso2] || [];
              GEO[iso2].push(f.geometry);
            }
            Object.keys(iso3).forEach((id) => {
              const isUnitedStatesTerritory = id === 'us' && ['ASM', 'GUM', 'MNP', 'PRI', 'UMI', 'VIR'].includes(iso);
              if (iso3[id].includes(iso) || isUnitedStatesTerritory) {
                GEO[id] = GEO[id] || [];
                if (!GEO[id].includes(f.geometry)) GEO[id].push(f.geometry);
              }
            });
          });
          buildCountryOutlines();
          setCountryOutlineActive(activeId());
          if (focusedId && !userZoomed && !userRotated) {
            targetZ = mentionGroup.children.length
              ? Math.max(IDLE_CAMERA_Z, focusCameraZ()) * (globalIssueRef.current ? GLOBAL_ISSUE_CAMERA_SCALE : 1)
              : countryFocusCameraZ(countries.find((c) => c.id === focusedId));
          }
          paintTone();
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
    let lastMoveAt = 0;
    let dragSamples = [];
    let activePointer = null;
    let caughtInertia = false;
    let selectionClearedDuringDrag = false;
    let spin = !reduced;
    setAutoSpin(spin);
    let focusRotation = null;
    let targetZ = IDLE_CAMERA_Z;
    let userZoomed = false;
    let userRotated = false;
    let focusedId = null;
    let highlightId = null; /* 목록만 좁힌 상태(줌 없이 윤곽만 강조) */
    const activeId = () => focusedId || highlightId;
    const focusCameraZ = () => {
      const verticalHalfFov = THREE.MathUtils.degToRad(cam.fov / 2);
      const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * cam.aspect);
      const limitingHalfFov = Math.min(verticalHalfFov, horizontalHalfFov);
      return VISIBLE_GLOBE_RADIUS / Math.sin(limitingHalfFov * FOCUS_FILL_RATIO);
    };
    const countryFocusCameraZ = (c) => {
      if (globalIssueRef.current) return Math.max(IDLE_CAMERA_Z, focusCameraZ()) * GLOBAL_ISSUE_CAMERA_SCALE;
      if (!c) return focusCameraZ();
      return countryCameraZ({
        rings: countryRings(c), lat: c.lat, lon: c.lon,
        ...orientTo(c.lat, c.lon), fov: cam.fov, aspect: cam.aspect,
        maxZ: focusCameraZ(),
      });
    };
    const clampCameraZ = (z) => Math.max(
      MIN_CAMERA_Z,
      Math.min(Math.max(IDLE_CAMERA_Z, focusCameraZ()) * 2, z),
    );

    const hitTargets = () =>
      beacons.filter((b) => b.visible).concat(pinHeads, countryLabels, countryHoverTargets, mentionGroup.children);
    const pickHit = () => {
      const surface = ray.ray.intersectSphere(new THREE.Sphere(globe.getWorldPosition(new THREE.Vector3()), 1), new THREE.Vector3());
      const surfaceDistance = surface ? surface.distanceTo(ray.ray.origin) : Infinity;
      return ray.intersectObjects(hitTargets()).find((hit) => hit.distance <= surfaceDistance + 0.015);
    };

    const onDown = (e) => {
      if (timeMachineRef.current) return;
      if (e.target !== renderer.domElement) return;
      if (!firstFrameRendered || e.button !== 0 || e.isPrimary === false || activePointer !== null) return;
      activePointer = e.pointerId;
      caughtInertia = Math.hypot(vx, vy) > 0.15;
      // 클릭 대상과 캡처 대상을 canvas로 통일한다. 부모가 캡처하면 click이 부모로 재지정된다.
      renderer.domElement.setPointerCapture?.(e.pointerId);
      dragging = true;
      vx = 0;
      vy = 0;
      lastMoveAt = e.timeStamp;
      dragSamples = [{ x: e.clientX, y: e.clientY, time: lastMoveAt }];
      px = e.clientX;
      py = e.clientY;
      dragDistance = 0;
      selectionClearedDuringDrag = false;
      wrap.classList.add(s.dragging);
      spin = false;
      setAutoSpin(false);
      focusRotation = null;
    };
    const onUp = (e) => {
      if (!dragging || e.pointerId !== activePointer) return;
      if (e.type === 'pointercancel' || reduced || dragDistance < 5
          || e.timeStamp - lastMoveAt > 100) {
        vx = 0;
        vy = 0;
      } else {
        ({ yaw: vx, pitch: vy } = globeReleaseVelocity(dragSamples, e.timeStamp));
      }
      if (renderer.domElement.hasPointerCapture?.(e.pointerId)) renderer.domElement.releasePointerCapture(e.pointerId);
      activePointer = null;
      dragSamples = [];
      dragging = false;
      wrap.classList.remove(s.dragging);
    };
    const onMove = (e) => {
      if (!firstFrameRendered) return;
      if (dragging && e.pointerId !== activePointer) return;
      if (dragging) {
        const dx = e.clientX - px;
        const dy = e.clientY - py;
        if (dx || dy) userRotated = true;
        dragDistance += Math.hypot(dx, dy);
        if (!selectionClearedDuringDrag && dragDistance >= 3 && cb.current.onGlobeMove) {
          selectionClearedDuringDrag = true;
          userClearedFocusRef.current = true;
          targetZ = cam.position.z;
          cb.current.onGlobeMove();
        }
        const now = e.timeStamp;
        lastMoveAt = now;
        dragSamples.push({ x: e.clientX, y: e.clientY, time: now });
        while (dragSamples.length > 2 && now - dragSamples[1].time > 100) dragSamples.shift();
        globe.rotation.y += dx * 0.0045;
        globe.rotation.x = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, globe.rotation.x + dy * 0.0045));
        px = e.clientX;
        py = e.clientY;
      }
      const r = wrap.getBoundingClientRect();
      mouse.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      mouse.y = -((e.clientY - r.top) / r.height) * 2 + 1;
      ray.setFromCamera(mouse, cam);
      const hit = pickHit();
      const tip = tipRef.current;
      if (hit && e.target === renderer.domElement) {
        tip.classList.add(s.show);
        tip.style.left = `${e.clientX - r.left}px`;
        tip.style.top = `${e.clientY - r.top}px`;
        const u = hit.object.userData;
        setCountryOutlineActive(u.type === 'mention' ? activeId() : u.cid || u.id);
        let tt;
        if (u.type === 'mention') {
          tt = `<b>${escapeHtml(u.fromName)} → ${escapeHtml(u.toName)}</b><br>국가명 언급 비율 ${(u.ratio * 100).toFixed(1)}%`;
        } else if (u.type === 'pin') {
          tt = `📌 <b>${escapeHtml(u.title)}</b><br>클릭하면 기사로 이동`;
        } else {
          tt = `${escapeHtml(u.flag)} <b>${escapeHtml(u.name)}</b> · ${escapeHtml(cb.current.countryClickHint)}`;
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
    const onWheel = (e) => {
      if (timeMachineRef.current) return;
      if (!firstFrameRendered) return;
      // Ctrl+휠은 브라우저 확대/축소에 맡기고, 지구본 위의 일반 휠만 처리한다.
      if (e.ctrlKey || !Number.isFinite(e.deltaY) || e.deltaY === 0) return;
      vx = 0;
      vy = 0;
      e.preventDefault();
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? wrap.clientHeight : 1;
      const delta = Math.max(-200, Math.min(200, e.deltaY * unit));
      targetZ = clampCameraZ(targetZ * Math.exp(delta * WHEEL_ZOOM_SPEED));
      userZoomed = true;
      if (cb.current.onGlobeMove) {
        userClearedFocusRef.current = true;
        cb.current.onGlobeMove();
      }
      tipRef.current?.classList.remove(s.show);
    };
    const onClick = (e) => {
      if (e.target !== renderer.domElement) return;
      if (!firstFrameRendered) return;
      if (dragDistance >= 5 || selectionClearedDuringDrag || caughtInertia) {
        dragDistance = 0;
        selectionClearedDuringDrag = false;
        caughtInertia = false;
        return;
      }
      const bounds = wrap.getBoundingClientRect();
      mouse.set(((e.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((e.clientY - bounds.top) / bounds.height) * 2 + 1);
      ray.setFromCamera(mouse, cam);
      const hit = pickHit();
      if (!hit) {
        const country = countryAtSurface();
        if (country) cb.current.onOpenCountry?.(country.id);
        return;
      }
      const u = hit.object.userData;
      if (u.type === 'mention') return;
      if (u.type === 'pin') {
        cb.current.onSelectPin?.(u);
        return;
      }
      cb.current.onOpenCountry?.(u.id);
    };

    wrap.addEventListener('pointerdown', onDown);
    addEventListener('pointerup', onUp);
    addEventListener('pointercancel', onUp);
    addEventListener('pointermove', onMove);
    wrap.addEventListener('click', onClick);
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });

    /* ── 루프 ── */
    const resize = () => {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
      if (userZoomed) targetZ = clampCameraZ(targetZ);
      else if (focusedId && !userRotated) {
        targetZ = mentionGroup.children.length
          ? Math.max(IDLE_CAMERA_Z, focusCameraZ()) * (globalIssueRef.current ? GLOBAL_ISSUE_CAMERA_SCALE : 1)
          : countryFocusCameraZ(countries.find((c) => c.id === focusedId));
      }
    };
    addEventListener('resize', resize);
    const sizeObserver = new ResizeObserver(resize);
    sizeObserver.observe(wrap);
    resize();

    let t = 0;
    let raf = 0;
    let lastFrameAt = performance.now();
    const calloutAnchors = new Map(countries.map((country) => [country.id, ll2v(country.lat, country.lon, 1.025)]));
    const anchorWorld = new THREE.Vector3();
    const anchorNormal = new THREE.Vector3();
    const anchorToCamera = new THREE.Vector3();
    const projectedAnchor = new THREE.Vector3();
    const calloutMotion = { countryId: null, side: null, x: null, y: null, change: null };
    const packets = [null, null];
    let nextTransmission = 0;
    let transmissionCountry = 0;
    const projectCountry = (id) => {
      const anchor = calloutAnchors.get(id);
      if (!anchor) return null;
      anchorWorld.copy(anchor).applyMatrix4(globe.matrixWorld);
      anchorNormal.copy(anchorWorld).sub(globe.position).normalize();
      anchorToCamera.copy(cam.position).sub(anchorWorld);
      projectedAnchor.copy(anchorWorld).project(cam);
      if (anchorNormal.dot(anchorToCamera) <= .12 || projectedAnchor.z >= 1
        || Math.abs(projectedAnchor.x) > .94 || Math.abs(projectedAnchor.y) > .86) return null;
      return { x: (projectedAnchor.x + 1) * wrap.clientWidth / 2, y: (1 - projectedAnchor.y) * wrap.clientHeight / 2 };
    };
    const updateSatellite = (now) => {
      const satellite = satelliteRef.current;
      if (!satellite) return;
      const active = satelliteDemoRef.current && !reduced && travelRef.current == null && !document.hidden;
      if (!active) {
        packets.fill(null);
        signalRefs.current.forEach((node) => node?.setAttribute('visibility', 'hidden'));
        nextTransmission = now + 1000;
        return;
      }
      if (now >= nextTransmission) {
        const slot = packets.findIndex((packet) => !packet);
        if (slot >= 0) {
          for (let i = 0; i < countries.length; i++) {
            const country = countries[transmissionCountry++ % countries.length];
            if (projectCountry(country.id)) { packets[slot] = { id: country.id, born: now }; break; }
          }
        }
        nextTransmission = now + 2400;
      }
      const end = { x: satellite.offsetLeft + satellite.offsetWidth * .28, y: satellite.offsetTop + satellite.offsetHeight * .41 };
      packets.forEach((packet, index) => {
        const node = signalRefs.current[index];
        if (!node) return;
        const start = packet && projectCountry(packet.id);
        const progress = packet ? (now - packet.born) / 3000 : 1;
        if (!start || progress >= 1) {
          packets[index] = null;
          node.setAttribute('visibility', 'hidden');
          return;
        }
        const control = { x: start.x + (end.x - start.x) * .35, y: Math.min(start.y, end.y) - 60 };
        const t = progress, u = 1 - t;
        const x = u * u * start.x + 2 * u * t * control.x + t * t * end.x;
        const y = u * u * start.y + 2 * u * t * control.y + t * t * end.y;
        const [trail, origin, halo, dot] = node.children;
        trail.setAttribute('d', `M${start.x} ${start.y}Q${control.x} ${control.y} ${end.x} ${end.y}`);
        origin.setAttribute('cx', start.x); origin.setAttribute('cy', start.y);
        [halo, dot].forEach((circle) => { circle.setAttribute('cx', x); circle.setAttribute('cy', y); });
        node.setAttribute('opacity', Math.min(1, progress * 8, (1 - progress) * 8));
        node.setAttribute('visibility', 'visible');
      });
    };
    let lastCardMotionAt = 0;
    const positionIssueCards = (now) => {
      const moving = spin || dragging || focusRotation || vx || vy
        || Math.abs(cam.position.z - targetZ) > 0.015;
      if (moving) lastCardMotionAt = now;
      if (moving || now - lastCardMotionAt < 160) {
        issueCardRefs.current.forEach((card) => { card.style.visibility = 'hidden'; });
        return;
      }
      // Do not move a button out from under the pointer between pointerdown and click.
      if (hoveredIssueCardRef.current && issueCardRefs.current.has(hoveredIssueCardRef.current)) return;
      const satellite = satelliteRef.current;
      const firstCard = issueCardRefs.current.values().next().value;
      if (!firstCard) return;
      const slots = issueCardSlots({ width: wrap.clientWidth, height: wrap.clientHeight,
        cardWidth: firstCard.offsetWidth, cardHeight: firstCard.offsetHeight,
        satelliteBottom: satellite ? satellite.offsetTop + satellite.offsetHeight : 0 });
      const projected = [];
      for (const row of issueCardsRef.current) {
        const id = row.country.countryCode.toLowerCase();
        const card = issueCardRefs.current.get(id);
        if (!card) continue;
        const anchor = calloutAnchors.get(id);
        if (!anchor) { card.style.visibility = 'hidden'; continue; }
        anchorWorld.copy(anchor).applyMatrix4(globe.matrixWorld);
        anchorNormal.copy(anchorWorld).sub(globe.position).normalize();
        anchorToCamera.copy(cam.position).sub(anchorWorld);
        const back = anchorNormal.dot(anchorToCamera) <= .04;
        projectedAnchor.copy(anchorWorld).project(cam);
        projected.push({ id, back, x: (projectedAnchor.x + 1) * wrap.clientWidth / 2,
          y: (1 - projectedAnchor.y) * wrap.clientHeight / 2 });
      }
      const placements = placeIssueCards({ rows: projected, slots, selectedId: selectedIssueCountryRef.current,
        width: wrap.clientWidth, height: wrap.clientHeight, cardWidth: firstCard.offsetWidth, cardHeight: firstCard.offsetHeight,
        obstacles: satellite ? [{ x: satellite.offsetLeft, y: satellite.offsetTop, width: satellite.offsetWidth, height: satellite.offsetHeight }] : [] });
      const byId = new Map(placements.map((placement) => [placement.id, placement]));
      for (const [id, card] of issueCardRefs.current) {
        const placement = byId.get(id);
        card.style.visibility = placement ? 'visible' : 'hidden';
        if (placement) {
          card.dataset.back = String(placement.back);
          card.style.transform = `translate3d(${placement.x}px, ${placement.y}px, 0)`;
        }
      }
    };
    const positionCallout = (now, elapsedMs) => {
      const card = calloutRef.current;
      const line = calloutLineRef.current;
      const dot = calloutAnchorRef.current;
      if (!card || !line || !dot) return;
      const country = countries.find((item) => item.id === calloutCountryRef.current);
      if (!country) return;

      globe.updateMatrixWorld(true);
      cam.updateMatrixWorld();
      anchorWorld.copy(calloutAnchors.get(country.id)).applyMatrix4(globe.matrixWorld);
      anchorNormal.copy(anchorWorld).sub(globe.position).normalize();
      anchorToCamera.copy(cam.position).sub(anchorWorld);
      projectedAnchor.copy(anchorWorld).project(cam);
      const visible = anchorNormal.dot(anchorToCamera) > 0.04
        && projectedAnchor.z < 1 && Math.abs(projectedAnchor.x) < 1 && Math.abs(projectedAnchor.y) < 1;
      if (!visible) {
        card.style.visibility = 'hidden';
        line.style.visibility = 'hidden';
        dot.style.visibility = 'hidden';
        calloutMotion.x = null;
        calloutMotion.y = null;
        return;
      }

      const x = (projectedAnchor.x + 1) * wrap.clientWidth / 2;
      const y = (1 - projectedAnchor.y) * wrap.clientHeight / 2;
      const { width, height } = calloutSizeRef.current;
      if (!width || !height) return;
      card.style.visibility = 'visible';
      line.style.visibility = 'visible';
      dot.style.visibility = 'visible';

      if (calloutMotion.countryId !== country.id) {
        calloutMotion.countryId = country.id;
        calloutMotion.side = null;
        calloutMotion.x = null;
        calloutMotion.y = null;
        calloutMotion.change = null;
      }
      const desiredSide = resolveGlobeCalloutSide({
        x, width, stageWidth: wrap.clientWidth,
        preferRight: country.lon >= 0, currentSide: calloutMotion.side,
      });
      if (!calloutMotion.side || reduced) calloutMotion.side = desiredSide;
      else if (desiredSide !== calloutMotion.side && !calloutMotion.change) {
        calloutMotion.change = { to: desiredSide, startedAt: now, relocated: false };
      }
      let opacity = 1;
      if (calloutMotion.change) {
        const age = now - calloutMotion.change.startedAt;
        if (age < 120) opacity = 1 - age / 120;
        else {
          if (!calloutMotion.change.relocated) {
            calloutMotion.side = calloutMotion.change.to;
            calloutMotion.x = null;
            calloutMotion.y = null;
            calloutMotion.change.relocated = true;
          }
          if (age < 280) opacity = (age - 120) / 160;
          else calloutMotion.change = null;
        }
      }
      const placement = layoutGlobeCallout({
        x, y, width, height, stageWidth: wrap.clientWidth, stageHeight: wrap.clientHeight,
        preferRight: country.lon >= 0, latitude: country.lat,
        side: calloutMotion.side, verticalBelow: country.lat < 45,
      });
      const follow = reduced || elapsedMs > 250 ? 1 : 1 - Math.exp(-elapsedMs / 90);
      calloutMotion.x = calloutMotion.x === null ? placement.cardX
        : calloutMotion.x + (placement.cardX - calloutMotion.x) * follow;
      calloutMotion.y = calloutMotion.y === null ? placement.cardY
        : calloutMotion.y + (placement.cardY - calloutMotion.y) * follow;
      card.style.transform = `translate3d(${calloutMotion.x}px, ${calloutMotion.y}px, 0)`;
      card.style.opacity = opacity;
      line.style.opacity = opacity;
      line.setAttribute('x1', x);
      line.setAttribute('y1', y);
      line.setAttribute('x2', placement.lineX + calloutMotion.x - placement.cardX);
      line.setAttribute('y2', placement.lineY + calloutMotion.y - placement.cardY);
      dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    };
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const now = performance.now();
      const elapsedMs = now - lastFrameAt;
      lastFrameAt = now;
      // 로딩 중에는 초기 방향을 유지한다. 실제 텍스처로 첫 프레임을 그린 뒤 공개한다.
      if (!textureReady) return;
      t += 0.016;
      const travel = travelRef.current;
      const machine = timeMachineRef.current;
      if (machine && travel == null) {
        vx = 0;
        vy = 0;
        const pacific = orientTo(0, -160);
        const follow = reduced ? 1 : 1 - Math.exp(-Math.min(elapsedMs, 50) / 160);
        globe.rotation.x += (pacific.pitch - globe.rotation.x) * follow;
        globe.rotation.y += shortestAngle(globe.rotation.y, pacific.yaw) * follow;
        globe.rotation.z += (0 - globe.rotation.z) * follow;
        if (Math.abs(globe.rotation.x - pacific.pitch) < 0.001
            && Math.abs(shortestAngle(globe.rotation.y, pacific.yaw)) < 0.001) {
          globe.rotation.set(pacific.pitch, pacific.yaw, 0);
        }
      }
      else if (travel != null) {
        vx = 0;
        vy = 0;
        const progress = Math.max(0, Math.min(1, travel));
        // Keep accelerating through arrival, with a stronger surge in the final stretch.
        const speed = 0.0003 + 0.012 * progress * progress + 0.028 * Math.pow(progress, 5);
        if (!reduced) globe.rotation.y += travelDirectionRef.current * Math.min(elapsedMs, 50) * speed;
      }
      else if (spin) globe.rotation.y += 0.0016;
      else if (!dragging && !focusRotation && !reduced && (vx || vy)) {
        if (elapsedMs > 250) {
          vx = 0;
          vy = 0;
        } else {
          const next = advanceGlobeInertia(globe.rotation.y, globe.rotation.x,
            vx, vy, elapsedMs, PITCH_LIMIT);
          globe.rotation.y = next.yaw;
          globe.rotation.x = next.pitch;
          vx = next.yawSpeed;
          vy = next.pitchSpeed;
        }
      }
      if (focusRotation && travel == null && !machine) {
        globe.rotation.x += (focusRotation.pitch - globe.rotation.x) * COUNTRY_FOCUS_LERP;
        globe.rotation.y += (focusRotation.yaw - globe.rotation.y) * COUNTRY_FOCUS_LERP;
        globe.rotation.z += (0 - globe.rotation.z) * COUNTRY_FOCUS_LERP;
        if (
          Math.abs(focusRotation.pitch - globe.rotation.x) < 0.005
          && Math.abs(focusRotation.yaw - globe.rotation.y) < 0.005
        ) {
          globe.rotation.set(focusRotation.pitch, focusRotation.yaw, 0);
          focusRotation = null;
        }
      }
      const zoomLerp = focusedId && !userZoomed && !userRotated ? COUNTRY_FOCUS_LERP : CAMERA_LERP;
      cam.position.z += ((machine ? IDLE_CAMERA_Z : targetZ) - cam.position.z) * zoomLerp;
      if (!reduced) {
        rings.forEach((r) => {
          const sc = 1 + 0.55 * (Math.sin(t * 2.2 + r.userData.t) * 0.5 + 0.5);
          r.scale.setScalar(sc);
          r.material.opacity = 0.85 - (sc - 1) * 1.1;
        });
        meteorTick();
      }
      fxTick(t);
      updateMentionFlow(mentionGroup, performance.now() / 1000, reduced);
      renderer.render(scene, cam);
      positionCallout(now, elapsedMs);
      positionIssueCards(now);
      updateSatellite(now);
      if (!firstFrameRendered) {
        firstFrameRendered = true;
        setEarthStatus('ready');
      }
    };
    loop();

    buildCountryLabels();
    buildCountryOutlines();
    loadGeo(); /* 국가 외곽선 전개·여론 톤 채색에 공용 */

    /* ── 바깥에서 쓰는 명령형 API ── */
    apiRef.current = {
      retryEarth() {
        if (!textureReady) startEarthLoad();
      },
      setMentions(links) {
        const hadLinks = mentionGroup.children.length > 0;
        globe.remove(mentionGroup);
        disposeObj(mentionGroup);
        mentionGroup = createMentionGroup(links);
        globe.add(mentionGroup);
        if (links.length) targetZ = Math.max(IDLE_CAMERA_Z, focusCameraZ());
        else if (hadLinks && focusedId) targetZ = countryFocusCameraZ(countries.find((c) => c.id === focusedId));
      },
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
        setCountryOutlineActive(activeId());
      },
      focusCountry(id) {
        const c = countries.find((x) => x.id === id);
        if (!c) return;
        vx = 0;
        vy = 0;
        focusedId = id;
        clearCountryFx();
        /* 나라를 정면에 세우되 북쪽은 위로 — 세계지도와 같은 자세다 */
        const target = orientTo(c.lat, c.lon);
        focusRotation = {
          pitch: target.pitch,
          yaw: globe.rotation.y + shortestAngle(globe.rotation.y, target.yaw),
        };
        /* 국가 본토 주변에 여백을 남기고, 작은 나라의 과도한 확대를 막는다. */
        targetZ = countryFocusCameraZ(c);
        userZoomed = false;
        userRotated = false;
        spin = false;
        setAutoSpin(false);
        syncBeacons(id);
        setCountryOutlineActive(id);
        paintTone();
        spawnCountryFx(c);
      },
      reset() {
        vx = 0;
        vy = 0;
        focusedId = null;
        focusRotation = null;
        targetZ = globalIssueRef.current ? Math.max(IDLE_CAMERA_Z, focusCameraZ()) * GLOBAL_ISSUE_CAMERA_SCALE : IDLE_CAMERA_Z;
        userZoomed = false;
        userRotated = false;
        spin = !reduced;
        setAutoSpin(spin);
        clearCountryFx();
        setCountryOutlineActive(highlightId);
        syncBeacons(highlightId);
        paintTone();
      },
      releaseFocus() {
        focusedId = null;
        focusRotation = null;
        userZoomed = true;
        userRotated = true;
        clearCountryFx();
        setCountryOutlineActive(highlightId);
        syncBeacons(highlightId);
        paintTone();
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
        vx = 0;
        vy = 0;
        setAutoSpin(!!on);
      },
      spawnMeteor,
    };

    return () => {
      cancelAnimationFrame(raf);
      disposeEarthTexture();
      delete wrap.dataset.earthTexture;
      removeEventListener('resize', resize);
      sizeObserver.disconnect();
      removeEventListener('pointerup', onUp);
      removeEventListener('pointercancel', onUp);
      removeEventListener('pointermove', onMove);
      wrap.removeEventListener('pointerdown', onDown);
      wrap.removeEventListener('click', onClick);
      renderer.domElement.removeEventListener('wheel', onWheel);
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
    if (userClearedFocusRef.current) {
      userClearedFocusRef.current = false;
      apiRef.current?.releaseFocus();
    } else if (focus) apiRef.current?.focusCountry(focus);
    else apiRef.current?.reset();
  }, [focus, calloutCountry, globalIssueView]);

  useEffect(() => {
    apiRef.current?.setMentions(mentionRelations);
  }, [mentionRelations, focus]);

  useEffect(() => {
    apiRef.current?.setHighlight(highlight);
  }, [highlight]);

  useEffect(() => {
    const card = calloutRef.current;
    if (!card) return undefined;
    const measure = () => { calloutSizeRef.current = { width: card.offsetWidth, height: card.offsetHeight }; };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(card);
    return () => { observer.disconnect(); calloutSizeRef.current = { width: 0, height: 0 }; };
  }, [calloutCountry, earthStatus]);

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
        className={`${s.canvas} ${earthStatus === 'ready' ? s.ready : s.pending}`}
        aria-busy={earthStatus === 'loading'}
        role="application"
        aria-label={`분석 대상 국가가 표시된 3D 지구본. 국가를 ${countryClickHint}.`}
      />
      {earthStatus !== 'ready' && <div className={s.loadingOverlay}>
        {earthStatus === 'error' ? <div role="alert">
          <p>지구를 불러오지 못했습니다.</p>
          <button type="button" onClick={() => apiRef.current?.retryEarth()}>다시 시도</button>
        </div> : <p role="status">지구를 불러오는 중…</p>}
      </div>}
      <div className={s.tip} ref={tipRef} />
      {earthStatus === 'ready' && <SatelliteRelay departing={timeMachineActive} satelliteRef={satelliteRef} signalRefs={signalRefs} />}
      {earthStatus === 'ready' && calloutCountry && callout && <>
        <svg className={s.analysisLink} style={{ '--analysis-tone-rgb': calloutToneColor }} aria-hidden="true"><line ref={calloutLineRef} /></svg>
        <span className={s.analysisAnchor} style={{ '--analysis-tone-rgb': calloutToneColor }} ref={calloutAnchorRef} aria-hidden="true" />
        <div className={s.analysisCallout} ref={calloutRef}>{callout}</div>
      </>}
      {earthStatus === 'ready' && issueCards.map((row) => {
        const id = row.country.countryCode.toLowerCase();
        const country = countries.find((item) => item.id === id);
        const score = scoreOf(row.toneAvg);
        return <button type="button" key={id} ref={(node) => { if (node) issueCardRefs.current.set(id, node); else issueCardRefs.current.delete(id); }}
          className={`${s.issueCard} ${selectedIssueCountry === id ? s.issueCardSelected : ''}`}
          style={{ '--issue-tone': score == null ? NO_SAMPLE.join(',') : toneRGB(score).join(',') }}
          aria-label={`${row.country.countryName}, ${score == null ? '논조 분석 없음' : toneLabel3(score)}, 관련 기사 ${row.articleCount}건`}
          aria-pressed={selectedIssueCountry === id}
          onPointerEnter={() => { hoveredIssueCardRef.current = id; }}
          onPointerLeave={() => { hoveredIssueCardRef.current = null; }}
          onPointerDown={(event) => { event.stopPropagation(); hoveredIssueCardRef.current = id; }}
          onPointerCancel={() => { hoveredIssueCardRef.current = null; }}
          onClick={(event) => { event.stopPropagation(); (onSelectIssueCountry || onOpenCountry)?.(id); if (event.detail === 0 || event.nativeEvent.pointerType === 'touch') hoveredIssueCardRef.current = null; }}>
          <span className={s.issueFlag} aria-hidden="true">{country?.flagImage
            ? <img src={country.flagImage} alt="" />
            : country?.flagClass ? <i className={country.flagClass} /> : flagOf(id)}</span>
          <strong>{row.country.countryName}</strong>
        </button>;
      })}
      {issueCards.length > 0 && <div className={s.issueLegend}>국가별 언론의 보도 관점<small></small><span><b style={{ color: '#d94b57' }}>● 부정</b>　<b style={{ color: '#9ea7b4' }}>● 중립</b>　<b style={{ color: '#1f9d6b' }}>● 긍정</b></span></div>}
      {children}
      {earthStatus === 'ready' && mentionRelations.length > 0 && <div className={s.relationsLegend} style={spinControl ? { bottom: 88 } : undefined} role="status">
        <span style={{ color: mentionRelations[0].incoming ? '#ffb454' : '#6fe7ff' }}>
          {mentionRelations[0].incoming ? '┄▶ 언급한 국가 → 선택 국가' : '┄▶ 선택 국가 → 언급한 국가'}
        </span>
        <small>언급 비율이 높을수록 굵은 선 · 선 위에 마우스를 올려 상세 확인</small>
      </div>}
      {spinControl && (
        <div className={s.spin} aria-label="지구 자전 제어">
          <button
            type="button"
            className={`${s.spinBtn} ${autoSpin ? s.on : ''}`}
            disabled={earthStatus !== 'ready'}
            title={autoSpin ? '지구 자전 멈춤' : '지구 자전 재개'}
            aria-label={autoSpin ? '지구 자전 멈춤' : '지구 자전 재개'}
            aria-pressed={autoSpin}
            onClick={() => {
              if (calloutCountryRef.current && cb.current.onGlobeMove) {
                userClearedFocusRef.current = true;
                cb.current.onGlobeMove();
              }
              apiRef.current?.setSpin(!autoSpin);
            }}
          >
            <span className={autoSpin ? s.spinningIcon : undefined} aria-hidden="true">{autoSpin ? '↻' : '▶'}</span>
            <span>{autoSpin ? '자전 중' : '자전 재개'}</span>
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
