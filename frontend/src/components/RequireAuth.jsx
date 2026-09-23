import PropTypes from 'prop-types';
import { Navigate, useLocation } from 'react-router-dom';
import useAuth from '../hooks/useAuth';

/**
 * Only renders its children for a logged-in user (optionally with one of
 * `roles`); otherwise redirects to the login page or the dashboard.
 * @param {{children: React.ReactNode, roles?: string[]}} props
 * @returns {JSX.Element}
 */
export default function RequireAuth({ children, roles }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

RequireAuth.propTypes = {
  children: PropTypes.node.isRequired,
  roles: PropTypes.arrayOf(PropTypes.oneOf(['employee', 'engineer', 'admin'])),
};
