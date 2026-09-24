import { useCallback, useEffect, useState } from 'react';

/**
 * Load data from the API and track loading and error state.
 *
 * State only changes when a request finishes. "Loading" is derived by
 * comparing the request that produced the current result with the one that
 * is wanted now, so no state is set synchronously inside the effect.
 *
 * @param {function(): Promise<*>} loader Calls the API. Wrap it in useCallback so it
 *   only changes when its inputs change; each change triggers a new load.
 * @param {{refreshMs?: number}} [options] refreshMs: reload in the background this
 *   often while the tab is visible, so the page stays current without websockets.
 * @returns {{data: *, error: Error|null, loading: boolean, reload: function(): void, setData: function}}
 */
export default function useApiData(loader, { refreshMs = 0 } = {}) {
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState({
    loader: null, reloadKey: -1, data: null, error: null,
  });

  useEffect(() => {
    let cancelled = false;
    loader()
      .then((data) => {
        if (!cancelled) setResult({ loader, reloadKey, data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setResult({ loader, reloadKey, data: null, error });
      });
    // Ignore results from a request that was superseded by a newer one.
    return () => { cancelled = true; };
  }, [loader, reloadKey]);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    if (!refreshMs) return undefined;
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') reload();
    }, refreshMs);
    return () => clearInterval(timer);
  }, [refreshMs, reload]);
  const setData = useCallback((data) => setResult((current) => ({ ...current, data })), []);

  const sameQuery = result.loader === loader;
  const loading = !sameQuery || result.reloadKey !== reloadKey;
  return {
    // Keep showing the current data while it is being reloaded, but not data for a different query.
    data: sameQuery ? result.data : null,
    error: loading ? null : result.error,
    loading,
    reload,
    setData,
  };
}
