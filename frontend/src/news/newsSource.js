import { request } from '../data/api.js';

// UI는 이 계약만 사용한다: filters(options), list(query, options), detail(id, options).
export const httpNewsSource = {
  filters: ({ signal } = {}) => request('/articles/filters', { signal }),
  list: (query, { signal } = {}) => request('/articles', { signal, params: query }),
  detail: (id, { signal } = {}) => request(`/articles/${encodeURIComponent(id)}`, { signal }),
};
// The archive uses the backend by default. Set VITE_NEWS_SOURCE=mock only for demos.
export const isMockNews = import.meta.env?.VITE_NEWS_SOURCE === 'mock';
const source = () => isMockNews
  ? import('./newsMock.js').then((module) => module.mockNewsSource)
  : Promise.resolve(httpNewsSource);
export const newsSource = {
  filters: async (options) => (await source()).filters(options),
  list: async (query, options) => (await source()).list(query, options),
  detail: async (id, options) => (await source()).detail(id, options),
};
