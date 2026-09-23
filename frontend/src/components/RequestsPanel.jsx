import PropTypes from 'prop-types';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { REQUEST_LABELS, formatDateTime } from '../constants';

const MESSAGES = {
  close_approval: 'asked to close this ticket',
  reopen: 'asked to reopen this ticket',
};

/**
 * Pending close/reopen requests, shown at the top of a ticket. Admins get
 * Approve and Reject buttons.
 * @param {{requests: Object[], canDecide: boolean, onDecide: function(Object, string): void}} props
 * @returns {JSX.Element|null}
 */
export default function RequestsPanel({ requests, canDecide, onDecide }) {
  const pending = requests.filter((request) => request.status === 'pending');
  if (!pending.length) return null;

  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {pending.map((request) => (
        <Alert
          key={request.id}
          severity="warning"
          action={canDecide ? (
            <Stack direction="row" spacing={1}>
              <Button color="inherit" size="small" onClick={() => onDecide(request, 'approved')}>Approve</Button>
              <Button color="inherit" size="small" onClick={() => onDecide(request, 'rejected')}>Reject</Button>
            </Stack>
          ) : undefined}
        >
          <Typography variant="body2">
            <strong>{`${REQUEST_LABELS[request.type]} pending: `}</strong>
            {`${request.requested_by_name} ${MESSAGES[request.type]} on ${formatDateTime(request.requested_at)}.`}
          </Typography>
          {request.reason && <Typography variant="body2">{`Reason: ${request.reason}`}</Typography>}
          {!canDecide && <Typography variant="caption">Waiting for an admin to decide.</Typography>}
        </Alert>
      ))}
    </Stack>
  );
}

RequestsPanel.propTypes = {
  requests: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.number.isRequired,
    type: PropTypes.oneOf(['reopen', 'close_approval']).isRequired,
    status: PropTypes.string.isRequired,
    reason: PropTypes.string,
    requested_by_name: PropTypes.string.isRequired,
    requested_at: PropTypes.string.isRequired,
  })).isRequired,
  canDecide: PropTypes.bool.isRequired,
  onDecide: PropTypes.func.isRequired,
};
