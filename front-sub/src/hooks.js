import { useCallback, useEffect, useRef, useState } from 'react';

export function parseRoute(search) {
  const p = new URLSearchParams(search);
  const numeric = k => /^\d+$/.test(p.get(k) || '') ? p.get(k) : '';
  return { page: ['world', 'explore', 'my'].includes(p.get('page')) ? p.get('page') : 'world', issue: numeric('issue'), article: (p.get('article') || '').slice(0, 255), country: /^[A-Z]{2}$/.test(p.get('country') || '') ? p.get('country') : '', field: numeric('field'), theme: numeric('theme'), compare: [...new Set((p.get('compare') || '').split(',').filter(c => /^[A-Z]{2}$/.test(c)))].slice(0, 2) };
}
export function routeSearch(route) {
  const p = new URLSearchParams();
  Object.entries(route).forEach(([k, v]) => { const value = Array.isArray(v) ? v.join(',') : v; if (value && !(k === 'page' && value === 'world')) p.set(k, value); });
  return p.size ? `?${p}` : '';
}
export function useRoute() {
  const [route, setRoute] = useState(() => parseRoute(window.location.search));
  useEffect(() => { const update = () => setRoute(parseRoute(window.location.search)); window.addEventListener('popstate', update); return () => window.removeEventListener('popstate', update); }, []);
  const navigate = useCallback((next, replace = false) => { setRoute(old => { const value = typeof next === 'function' ? next(old) : next; const url = `/${routeSearch(value)}`; if (`${location.pathname}${location.search}` !== url) window.history[replace ? 'replaceState' : 'pushState']({}, '', url); return value; }); }, []);
  return [route, navigate];
}
export function useResource(key, loader) {
  const ref = useRef(loader); ref.current = loader;
  const [version, setVersion] = useState(0);
  const [state, setState] = useState({ key: null, loading: true });
  useEffect(() => {
    if (!key) return;
    const controller = new AbortController(); let active = true;
    setState(old => ({ key, data: old.key === key ? old.data : null, loading: true, error: null }));
    Promise.resolve().then(() => ref.current(controller.signal)).then(data => { if (active) setState({ key, data, loading: false, error: null }); }).catch(error => { if (active) setState(old => ({ ...old, loading: false, error: error.message })); });
    return () => { active = false; controller.abort(); };
  }, [key, version]);
  return { ...(state.key === key ? state : { loading: Boolean(key), data: null }), retry: () => setVersion(v => v + 1) };
}
export function useStored(key, fallback) {
  const [value, setValue] = useState(() => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } });
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage may be unavailable; session state still works. */ } }, [key, value]);
  return [value, setValue];
}
