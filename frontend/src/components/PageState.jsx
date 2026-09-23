import PropTypes from 'prop-types';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Typography from '@mui/material/Typography';
import InboxOutlinedIcon from '@mui/icons-material/InboxOutlined';

/**
 * Centered spinner for a loading page or panel.
 * @param {{label?: string}} props
 * @returns {JSX.Element}
 */
export function LoadingState({ label = 'Loading…' }) {
  return (
    <Box role="status" sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2, py: 6 }}>
      <CircularProgress size={28} />
      <Typography color="text.secondary">{label}</Typography>
    </Box>
  );
}

LoadingState.propTypes = {
  label: PropTypes.string,
};

/**
 * Error message with an optional retry button.
 * @param {{error: Error, onRetry?: function}} props
 * @returns {JSX.Element}
 */
export function ErrorState({ error, onRetry }) {
  return (
    <Alert
      severity="error"
      sx={{ my: 2 }}
      action={onRetry ? <Button color="inherit" size="small" onClick={onRetry}>Try again</Button> : undefined}
    >
      {error.message || 'Something went wrong.'}
    </Alert>
  );
}

ErrorState.propTypes = {
  error: PropTypes.instanceOf(Error).isRequired,
  onRetry: PropTypes.func,
};

/**
 * Friendly message when a list has nothing to show.
 * @param {{title: string, message?: string, action?: React.ReactNode}} props
 * @returns {JSX.Element}
 */
export function EmptyState({ title, message, action }) {
  return (
    <Box sx={{ textAlign: 'center', py: 6, color: 'text.secondary' }}>
      <InboxOutlinedIcon sx={{ fontSize: 48, mb: 1 }} aria-hidden />
      <Typography variant="h6" color="text.primary">{title}</Typography>
      {message && <Typography sx={{ mt: 0.5 }}>{message}</Typography>}
      {action && <Box sx={{ mt: 2 }}>{action}</Box>}
    </Box>
  );
}

EmptyState.propTypes = {
  title: PropTypes.string.isRequired,
  message: PropTypes.string,
  action: PropTypes.node,
};
