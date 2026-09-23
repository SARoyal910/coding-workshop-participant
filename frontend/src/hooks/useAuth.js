import { useContext } from 'react';
import { AuthContext } from '../context/contexts';

/**
 * Access the current user and auth actions from AuthProvider.
 * @returns {{user: Object|null, login: Function, register: Function, logout: Function, logoutMessage: string}}
 */
export default function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
