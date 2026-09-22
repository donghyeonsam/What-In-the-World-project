const EARTH_2K = '/earth.jpg';
const EARTH_4K = '/earth-4k.jpg?v=bathymetry-200407';
const EARTH_8K = '/earth-8k.jpg?v=bathymetry-200407';

// GPU 크기 제한은 성능 측정값이 아니므로 메모리·CPU·입력 장치도 함께 확인한다.
// 정보가 없는 브라우저는 보수적으로 4K를 선택한다.
export function earthTextureUrls({
  maxTextureSize = 0,
  deviceMemory = 0,
  hardwareConcurrency = 0,
  coarsePointer = true,
  saveData = false,
  customTexture,
}) {
  if (customTexture) return [customTexture];
  if (maxTextureSize < 4096) return [EARTH_2K];
  const canUse8k = maxTextureSize >= 8192 && deviceMemory >= 8
    && hardwareConcurrency >= 8 && !coarsePointer && !saveData;
  return canUse8k ? [EARTH_8K, EARTH_4K, EARTH_2K] : [EARTH_4K, EARTH_2K];
}

// 성공하면 추가 파일을 로드하지 않는다. 실패한 텍스처와 언마운트된 씬의
// 텍스처를 정리하고, 늦게 도착한 이미지가 폐기된 씬을 갱신하지 않도록 한다.
export function loadEarthTexture(loader, urls, { onLoad, onError }) {
  let stopped = false;
  const textures = new Set();
  const release = (texture) => {
    if (textures.delete(texture)) texture.dispose();
    texture.image = null;
  };
  const load = (index) => {
    const url = urls[index];
    const texture = loader.load(url, (loaded) => {
      if (stopped) {
        release(loaded);
        return;
      }
      onLoad(loaded, url);
    }, undefined, (error) => {
      release(texture);
      if (stopped) return;
      if (index + 1 < urls.length) load(index + 1);
      else onError?.(error);
    });
    textures.add(texture);
  };
  load(0);
  return () => {
    stopped = true;
    for (const texture of textures) release(texture);
  };
}
