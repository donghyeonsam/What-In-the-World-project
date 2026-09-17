const DEFAULT_AUTHORIZE_URL = 'https://project.ssafy.com/oauth/sso-check';
const SSAFY_CLIENT_ID = '86976ec9-cbb3-4768-a339-e03ce05e2e39';
const SSAFY_REDIRECT_URI = 'https://dev.witw.kro.kr/';
const STATE_KEY = 'witw_ssafy_oauth_state';
const RETURN_KEY = 'witw_ssafy_oauth_return';

export function createSsafyAuthorizeUrl(location, storage, randomUUID) {
  const state = randomUUID();
  storage.setItem(STATE_KEY, state);
  storage.setItem(RETURN_KEY, `${location.pathname}${location.search}${location.hash}`);

  const url = new URL(import.meta.env?.VITE_SSAFY_AUTHORIZE_URL || DEFAULT_AUTHORIZE_URL);
  url.searchParams.set('client_id', SSAFY_CLIENT_ID);
  url.searchParams.set('redirect_uri', SSAFY_REDIRECT_URI);
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('state', state);
  return url.toString();
}

export function beginSsafyLogin() {
  const url = createSsafyAuthorizeUrl(window.location, sessionStorage, () => crypto.randomUUID());
  window.location.assign(url);
}

export function readSsafyCallback(search, storage = sessionStorage) {
  const params = new URLSearchParams(search);
  const code = params.get('code');
  const providerError = params.get('error');
  if (!code && !providerError) return null;
  if (providerError) throw new Error(params.get('error_description') || 'SSAFY 로그인이 취소되었습니다.');

  const expected = storage.getItem(STATE_KEY);
  if (!expected || params.get('state') !== expected) {
    throw new Error('로그인 요청을 확인할 수 없습니다. 다시 시도해 주세요.');
  }
  storage.removeItem(STATE_KEY);
  const returnUrl = storage.getItem(RETURN_KEY) || window.location.pathname;
  storage.removeItem(RETURN_KEY);
  return { code, returnUrl };
}
