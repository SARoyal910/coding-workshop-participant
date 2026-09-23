import { useState } from 'react';
import {
  Link as RouterLink, Navigate, useLocation, useNavigate,
} from 'react-router-dom';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AuthCard from '../components/AuthCard';
import useAuth from '../hooks/useAuth';

/**
 * Login form. Shows the server's error (always "Invalid email or password" for
 * bad credentials) and the reason when the user was logged out automatically.
 * @returns {JSX.Element}
 */
export default function LoginPage() {
  const { user, login, logoutMessage } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={location.state?.from || '/'} replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(location.state?.from || '/', { replace: true });
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <AuthCard title="Log in" subtitle="Report and track facility and IT incidents.">
      <Stack component="form" spacing={2} onSubmit={handleSubmit} noValidate>
        {logoutMessage && !error && <Alert severity="info">{logoutMessage}</Alert>}
        {error && <Alert severity="error" role="alert">{error}</Alert>}
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          fullWidth
          autoFocus
          disabled={submitting}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          fullWidth
          disabled={submitting}
        />
        <Button type="submit" variant="contained" size="large" disabled={submitting || !email || !password}>
          {submitting ? 'Logging in…' : 'Log in'}
        </Button>
        <Typography variant="body2" color="text.secondary" align="center">
          New here?
          {' '}
          <Link component={RouterLink} to="/register">Create an account</Link>
        </Typography>
      </Stack>
    </AuthCard>
  );
}
