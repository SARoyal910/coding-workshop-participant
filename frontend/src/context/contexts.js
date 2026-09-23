import { createContext } from 'react';

/**
 * React context objects, kept apart from their providers so provider files only
 * export components (needed for fast refresh). Read them with hooks/useAuth
 * and hooks/useNotify.
 */
export const AuthContext = createContext(null);
export const NotifyContext = createContext(null);
