import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { COUNTRY_FOCUS_FILL, MIN_COUNTRY_CAMERA_Z, focusRingOf, countryCameraZ } from '../src/lib/globeFocus.js';

const rectangle = (west, south, east, north) => [
  [west, south], [east, south], [east, north], [west, north], [west, south],
];
const options = (rings, lat = 36.5, lon = 127.8, aspect = 1) => ({
  rings, lat, lon, pitch: Math.min(0.9, THREE.MathUtils.degToRad(lat)),
  yaw: THREE.MathUtils.degToRad(-(lon + 90)), fov: 38, aspect, maxZ: 6,
});

test('country focus leaves half of the viewport for surrounding context', () => {
  assert.equal(COUNTRY_FOCUS_FILL, 0.5);
  const config = options([rectangle(-125, 25, -67, 49)], 38, -97);
  const z = countryCameraZ(config);
  const camera = new THREE.PerspectiveCamera(config.fov, config.aspect, 0.1, 100);
  camera.position.z = z;
  camera.updateMatrixWorld();
  config.rings[0].forEach(([lon, lat]) => {
    const phi = THREE.MathUtils.degToRad(90 - lat);
    const theta = THREE.MathUtils.degToRad(lon + 180);
    const radius = 1.008 * 1.035;
    const projected = new THREE.Vector3(
      -radius * Math.sin(phi) * Math.cos(theta), radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.sin(theta),
    ).applyEuler(new THREE.Euler(config.pitch, config.yaw, 0)).project(camera);
    assert.ok(Math.abs(projected.x) <= COUNTRY_FOCUS_FILL + 1e-9);
    assert.ok(Math.abs(projected.y) <= COUNTRY_FOCUS_FILL + 1e-9);
  });
});

test('small countries stop at the automatic zoom limit, above manual wheel minimum', () => {
  const z = countryCameraZ(options([rectangle(127, 36, 128, 37)]));
  assert.equal(z, MIN_COUNTRY_CAMERA_Z);
  assert.ok(z > 1.5);
});

test('a larger country gets a more distant view than a small country', () => {
  const small = countryCameraZ(options([rectangle(127, 36, 128, 37)]));
  const large = countryCameraZ(options([rectangle(-125, 25, -67, 49)], 38, -97));
  assert.ok(large > small);
});

test('the mainland containing the country center wins over distant territories', () => {
  const alaska = rectangle(-170, 55, -130, 71);
  const mainland = rectangle(-125, 25, -67, 49);
  assert.equal(focusRingOf([alaska, mainland], 38, -97), mainland);
  assert.equal(countryCameraZ(options([alaska, mainland], 38, -97)),
    countryCameraZ(options([mainland], 38, -97)));
});

test('if the center is offshore, the nearest island is used', () => {
  const distant = rectangle(150, 30, 151, 31);
  const near = rectangle(138, 36, 139, 37);
  assert.equal(focusRingOf([distant, near], 36.5, 137.5), near);
});

test('a country across the date line still contains its center', () => {
  const ring = rectangle(178, -20, -178, -16);
  assert.equal(focusRingOf([rectangle(140, -20, 142, -16), ring], -18, 180), ring);
});

test('a narrower viewport backs off while a wide viewport does not overzoom', () => {
  const rings = [rectangle(-125, 25, -67, 49)];
  assert.ok(countryCameraZ(options(rings, 38, -97, 0.65))
    > countryCameraZ(options(rings, 38, -97, 1.6)));
});

test('auto focus never backs off beyond the whole-globe view and tolerates missing outlines', () => {
  const config = { ...options([rectangle(-125, 25, -67, 49)], 38, -97, 0.1), maxZ: 4 };
  assert.equal(countryCameraZ(config), 4);
  assert.equal(countryCameraZ({ ...config, rings: [] }), 4);
  assert.equal(countryCameraZ({ ...config, aspect: 0 }), 4);
});
