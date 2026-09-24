import { lazy } from 'react';

const RELOAD_KEY = 'reloadedForNewVersion';

/**
 * React.lazy that recovers from a new deploy. Each deploy replaces the page
 * files, so a tab opened before it asks for files that no longer exist. When
 * a page fails to load, reload once to pick up the new version. The flag
 * stops a reload loop if the page is genuinely broken; it is cleared as soon
 * as a page loads.
 * @param {function(): Promise<{default: React.ComponentType}>} load
 * @returns {React.LazyExoticComponent}
 */
export default function lazyWithReload(load) {
  return lazy(() => loadOrReload(load, () => window.location.reload()));
}

/**
 * Load a page module; if that fails for the first time this session, call
 * reload() and never settle. A second failure is thrown to the error boundary.
 * @param {function(): Promise<Object>} load
 * @param {function(): void} reload
 * @returns {Promise<Object>}
 */
export function loadOrReload(load, reload) {
  return load().then(
    (module) => {
      try {
        sessionStorage.removeItem(RELOAD_KEY);
      } catch {
        // Storage can be unavailable (private mode); nothing to clear.
      }
      return module;
    },
    (error) => {
      let reloaded = true;
      try {
        reloaded = sessionStorage.getItem(RELOAD_KEY) === '1';
        if (!reloaded) sessionStorage.setItem(RELOAD_KEY, '1');
      } catch {
        // Without storage we can't guard against a loop, so don't reload.
      }
      if (reloaded) throw error;
      reload();
      return new Promise(() => {}); // The page is reloading; never render.
    },
  );
}
