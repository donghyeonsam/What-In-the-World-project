const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function request(path, { signal, params = {}, method = 'GET', body: payload, allowEmpty = false } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  });
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timeout = setTimeout(() => controller.abort(new Error('요청 시간이 초과되었습니다.')), 15000);
  try {
    const response = await fetch(`${API_BASE}${path}${query.size ? `?${query}` : ''}`, {
      signal: controller.signal, method, credentials: 'include',
      headers: { Accept: 'application/json', ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body || body.status >= 400 || (!allowEmpty && !('data' in body))) {
      throw new ApiError(body?.message || `데이터를 불러오지 못했습니다 (${response.status}).`, response.status);
    }
    return body.data;
  } catch (error) {
    if (signal?.aborted || error instanceof ApiError) throw error;
    throw new ApiError(controller.signal.aborted ? '요청 시간이 초과되었습니다. 다시 시도해 주세요.' : '서버에 연결하지 못했습니다. 연결 상태를 확인해 주세요.');
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abort);
  }
}

export const api = {
  dashboard: (signal, asOf) => request('/global/issues', { signal, params: { asOf } }),
  fields: (signal, asOf) => request('/themes/by-field', { signal, params: { asOf } }),
  country: (code, signal, asOf) => request(`/countries/${encodeURIComponent(code.toUpperCase())}`, { signal, params: { asOf } }),
  popular: (code, signal, asOf) => request(`/countries/${encodeURIComponent(code.toUpperCase())}/themes/popular`, { signal, params: { limit: 10, asOf } }),
  theme: (id, countryCode, signal, asOf) => request(`/themes/${encodeURIComponent(id)}/overview`, { signal, params: { issueLimit: 10, articleLimit: 10, countryCode, asOf } }),
  issue: (id, signal, asOf) => request(`/global/issues/${encodeURIComponent(id)}`, { signal, params: { asOf } }),
  overview: (id, countryCode, signal, asOf) => request(`/issues/${encodeURIComponent(id)}/overview`, { signal, params: { articleLimit: 10, countryCode, asOf } }),
};
