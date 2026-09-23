import { useContext } from 'react';
import { NotifyContext } from '../context/contexts';

/**
 * Show a message: notify(text, 'success' | 'error' | 'info', {label, onClick}?).
 * @returns {{notify: function(string, string=, Object=): void}}
 */
export default function useNotify() {
  const context = useContext(NotifyContext);
  if (!context) throw new Error('useNotify must be used inside NotifyProvider');
  return context;
}
