import { useState } from 'react';
import { Link as RouterLink, Navigate, useNavigate } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AuthCard from '../components/AuthCard';
import useAuth from '../hooks/useAuth';
import useNotify from '../hooks/useNotify';

const EMAIL_DOMAIN = '@acme.inc';
const PASSWORD_MIN = 8;

/**
 * Check the form before sending it, with the same rules the API enforces.
 * @param {{name: string, email: string, password: string}} values
 * @returns {Object<string, string>} Field name -> message.
 */
function validate({ name, email, password }) {
  const errors = {};
  if (!name.trim()) errors.name = 'Enter your name';
  if (!email.trim().toLowerCase().endsWith(EMAIL_DOMAIN)) errors.email = `Use your ${EMAIL_DOMAIN} email address`;
  if (password.length < PASSWORD_MIN) errors.password = `At least ${PASSWORD_MIN} characters`;
  return errors;
}

/**
 * Self-registration for employees. Only @acme.inc emails are accepted; the
 * server always creates the account with the employee role.
 * @returns {JSX.Element}
 */
export default function RegisterPage() {
  const { user, register } = useAuth();
  const { notify } = useNotify();
  const navigate = useNavigate();
  const [values, setValues] = useState({ name: '', email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const handleChange = (field) => (event) => {
    setValues((current) => ({ ...current, [field]: event.target.value }));
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    const errors = validate(values);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    setSubmitting(true);
    try {
      await register(values.name.trim(), values.email.trim(), values.password);
      notify('Welcome! Your account is ready.');
      navigate('/', { replace: true });
    } catch (err) {
      setFieldErrors(err.details || {});
      setError(err.message);
      setSubmitting(false);
    }
  };

  const fieldProps = (field) => ({
    value: values[field],
    onChange: handleChange(field),
    error: Boolean(fieldErrors[field]),
    helperText: fieldErrors[field],
    disabled: submitting,
    required: true,
    fullWidth: true,
  });

  return (
    <AuthCard title="Create an account" subtitle="For ACME employees. Use your company email.">
      <Stack component="form" spacing={2} onSubmit={handleSubmit} noValidate>
        {error && <Alert severity="error" role="alert">{error}</Alert>}
        <TextField label="Full name" autoComplete="name" autoFocus {...fieldProps('name')} />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          placeholder={`you${EMAIL_DOMAIN}`}
          {...fieldProps('email')}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          {...fieldProps('password')}
          helperText={fieldErrors.password || `At least ${PASSWORD_MIN} characters`}
        />
        <Button type="submit" variant="contained" size="large" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
        <Typography variant="body2" color="text.secondary" align="center">
          Already have an account?
          {' '}
          <Link component={RouterLink} to="/login">Log in</Link>
        </Typography>
      </Stack>
    </AuthCard>
  );
}
