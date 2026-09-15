import test from 'node:test';
import assert from 'node:assert/strict';
import { earthTextureUrls, loadEarthTexture } from '../src/lib/earthTextures.js';

const desktop = {
  maxTextureSize: 16384, deviceMemory: 8, hardwareConcurrency: 8,
  coarsePointer: false, saveData: false,
};
const earth4k = '/earth-4k.jpg?v=bathymetry-200407';
const earth8k = '/earth-8k.jpg?v=bathymetry-200407';

test('8K is selected only with sufficient capabilities and device information', () => {
  assert.deepEqual(earthTextureUrls(desktop), [earth8k, earth4k, '/earth.jpg']);
  for (const condition of [
    { maxTextureSize: 4096 }, { deviceMemory: 4 }, { hardwareConcurrency: 4 },
    { deviceMemory: undefined }, { hardwareConcurrency: undefined },
    { coarsePointer: true }, { saveData: true },
  ]) {
    assert.deepEqual(earthTextureUrls({ ...desktop, ...condition }), [earth4k, '/earth.jpg']);
  }
});

test('GPU limits fall back to 2K and explicitly supplied textures retain their behavior', () => {
  assert.deepEqual(earthTextureUrls({ ...desktop, maxTextureSize: 2048 }), ['/earth.jpg']);
  assert.deepEqual(earthTextureUrls({ ...desktop, customTexture: '/custom.jpg' }), ['/custom.jpg']);
});

function fakeLoader() {
  const requests = [];
  return {
    requests,
    load(url, onLoad, _onProgress, onError) {
      const texture = { image: null, disposals: 0, dispose() { this.disposals++; } };
      requests.push({
        url, texture,
        resolve() { texture.image = { width: 8192, height: 4096 }; onLoad(texture); },
        reject() { onError(new Error(`Failed: ${url}`)); },
      });
      return texture;
    },
  };
}

test('a successful texture is reused without loading lower resolutions and disposed once', () => {
  const loader = fakeLoader();
  const loaded = [];
  const dispose = loadEarthTexture(loader, earthTextureUrls(desktop), {
    onLoad: (texture, url) => loaded.push({ texture, url }),
  });
  loader.requests[0].resolve();
  assert.equal(loader.requests.length, 1);
  assert.equal(loaded[0].url, earth8k);
  assert.equal(loaded[0].texture, loader.requests[0].texture);
  dispose();
  dispose();
  assert.equal(loaded[0].texture.disposals, 1);
  assert.equal(loaded[0].texture.image, null);
});

test('failed 8K loads fall back to 4K while releasing the failed texture', () => {
  const loader = fakeLoader();
  let activeUrl;
  const dispose = loadEarthTexture(loader, earthTextureUrls(desktop), {
    onLoad: (_texture, url) => { activeUrl = url; },
  });
  loader.requests[0].reject();
  assert.equal(loader.requests[0].texture.disposals, 1);
  assert.equal(loader.requests[1].url, earth4k);
  loader.requests[1].resolve();
  assert.equal(activeUrl, earth4k);
  assert.equal(loader.requests.length, 2);
  dispose();
  assert.equal(loader.requests[1].texture.disposals, 1);
});

test('exhausted fallback attempts report a single error and release all allocations', () => {
  const loader = fakeLoader();
  let errors = 0;
  const dispose = loadEarthTexture(loader, earthTextureUrls(desktop), {
    onLoad: () => assert.fail('Failed texture became active'),
    onError: () => { errors++; },
  });
  for (let i = 0; i < 3; i++) loader.requests[i].reject();
  assert.deepEqual(loader.requests.map((request) => request.url),
    [earth8k, earth4k, '/earth.jpg']);
  assert.equal(errors, 1);
  dispose();
  assert.ok(loader.requests.every((request) => request.texture.disposals === 1));
});

test('unmounted scenes ignore late success and release the decoded image', () => {
  const loader = fakeLoader();
  const dispose = loadEarthTexture(loader, earthTextureUrls(desktop), {
    onLoad: () => assert.fail('Disposed scene was updated'),
  });
  dispose();
  loader.requests[0].resolve();
  assert.equal(loader.requests[0].texture.image, null);
  assert.equal(loader.requests[0].texture.disposals, 1);
  assert.equal(loader.requests.length, 1);
});

test('late failure after unmount does not launch further downloads', () => {
  const loader = fakeLoader();
  const dispose = loadEarthTexture(loader, earthTextureUrls(desktop), {
    onLoad: () => assert.fail('Disposed scene was updated'),
    onError: () => assert.fail('Disposed scene reported a loading error'),
  });
  dispose();
  loader.requests[0].reject();
  assert.equal(loader.requests.length, 1);
  assert.equal(loader.requests[0].texture.disposals, 1);
});
