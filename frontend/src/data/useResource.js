import { useCallback, useEffect, useRef, useState } from 'react';

// Key changes hide the previous screen immediately; cleanup prevents late responses
// from replacing a newer country/theme selection, including React StrictMode.
export function useResource(key, loader, refreshMs = 0) {
  const loadRef = useRef(loader);
  loadRef.current = loader;
  const [version, setVersion] = useState(0);
  const [state, setState] = useState({ key: null, data: null, loading: true, error: null });
  const retry = useCallback(() => setVersion((value) => value + 1), []);
  useEffect(() => {
    if (key === null) return;
    let active = true;
    let timer;
    const controller = new AbortController();
    const run = async () => {
      setState((old) => ({ key, data: old.key === key ? old.data : null, loading: true, error: null }));
      try {
        const data = await loadRef.current(controller.signal);
        if (active) setState({ key, data, loading: false, error: null, updatedAt: new Date() });
      } catch (error) {
        if (active) setState((old) => ({ ...old, key, loading: false, error }));
      } finally {
        if (active && refreshMs) timer = setTimeout(run, refreshMs);
      }
    };
    run();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [key, version, refreshMs]);
  return { ...(state.key === key ? state : { data: null, loading: key !== null, error: null }), retry };
}
