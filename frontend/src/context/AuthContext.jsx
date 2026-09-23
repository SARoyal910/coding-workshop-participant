import {
  useCallback, useEffect, useMemo, useState,
} from 'react';
import PropTypes from 'prop-types';
import { AuthContext } from './contexts';
import {
  authApi, setAuthToken, setUnauthorizedHandler,
} from '../services/api';

const STORAGE_KEY = 'acme.session';
const REFRESH_BEFORE_MS = 30 * 60 * 1000; // Refresh when less than 30 minutes remain (13.6).


/**
 * Read the expiry time (ms) from a JWT without verifying it; the server verifies.
 * @param {string} token
 * @returns {number}
 */
function tokenExpiry(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp * 1000;
  } catch {
    return 0;
  }
}

/** Load a saved session from localStorage, ignoring anything broken or expired. */
function loadSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.token && tokenExpiry(saved.token) > Date.now()) return saved;
  } catch {
    // Storage unavailable or corrupted: start logged out.
  }
  return null;
}

/**
 * Holds the logged-in user and token, keeps the token fresh, and logs the user
 * out (with a message) when the API says the session is no longer valid.
 * @param {{children: React.ReactNode}} props
 * @returns {JSX.Element}
 */
export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    const saved = loadSession();
    setAuthToken(saved?.token || null);
    return saved;
  });
  const [logoutMessage, setLogoutMessage] = useState('');

  const saveSession = useCallback((next) => {
    setAuthToken(next?.token || null);
    setSession(next);
    try {
      if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // The session still works for this tab.
    }
  }, []);

  const logout = useCallback((message = '') => {
    setLogoutMessage(message);
    saveSession(null);
  }, [saveSession]);

  const login = useCallback(async (email, password) => {
    const data = await authApi.login(email, password);
    setLogoutMessage('');
    saveSession(data);
    return data.user;
  }, [saveSession]);

  const register = useCallback(async (name, email, password) => {
    const data = await authApi.register(name, email, password);
    setLogoutMessage('');
    saveSession(data);
    return data.user;
  }, [saveSession]);

  // Any 401 on an authenticated request ends the session.
  useEffect(() => {
    setUnauthorizedHandler(() => logout('Your session expired, please log in again.'));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Refresh the token shortly before it expires.
  useEffect(() => {
    if (!session?.token) return undefined;
    const delay = Math.max(tokenExpiry(session.token) - Date.now() - REFRESH_BEFORE_MS, 0);
    const timer = setTimeout(async () => {
      try {
        saveSession(await authApi.refresh());
      } catch {
        // A 401 here is handled by the unauthorized handler.
      }
    }, delay);
    return () => clearTimeout(timer);
  }, [session, saveSession]);

  const value = useMemo(() => ({
    user: session?.user || null,
    login,
    register,
    logout,
    logoutMessage,
  }), [session, login, register, logout, logoutMessage]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

AuthProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

