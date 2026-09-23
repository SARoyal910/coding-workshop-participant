import { useCallback, useState } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import TablePagination from '@mui/material/TablePagination';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';
import ActionDialog from '../components/ActionDialog';
import PriorityChip from '../components/PriorityChip';
import StatusChip from '../components/StatusChip';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useApiData from '../hooks/useApiData';
import useNotify from '../hooks/useNotify';
import { incidentsApi } from '../services/api';
import { REQUEST_LABELS, formatDateTime } from '../constants';

const PAGE_SIZE = 25;

/** What approving or rejecting does, per request type (matches the backend workflow). */
const OUTCOMES = {
  close_approval: {
    approved: 'The ticket is archived: read-only and hidden from active lists.',
    rejected: 'The ticket goes back to Resolved. Your note is shown on the ticket.',
  },
  reopen: {
    approved: 'The ticket goes back to In progress for the engineers on it.',
    rejected: 'The ticket stays as it is. Your note is shown on the ticket.',
  },
};

const requestShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  type: PropTypes.string.isRequired,
  reason: PropTypes.string,
  requested_at: PropTypes.string.isRequired,
  requested_by_name: PropTypes.string.isRequired,
  incident_id: PropTypes.number.isRequired,
  incident_title: PropTypes.string.isRequired,
  incident_status: PropTypes.string.isRequired,
  incident_priority: PropTypes.string.isRequired,
});

/**
 * One pending request with Approve / Reject buttons.
 * @param {{request: Object, onDecide: function(Object, string): void}} props
 * @returns {JSX.Element}
 */
function RequestItem({ request, onDecide }) {
  return (
    <Box sx={{ p: 2 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { md: 'center' } }}>
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={1} sx={{ mb: 0.5, flexWrap: 'wrap', gap: 0.5 }}>
            <Chip size="small" color={request.type === 'reopen' ? 'warning' : 'info'} label={REQUEST_LABELS[request.type]} />
            <StatusChip status={request.incident_status} />
            <PriorityChip priority={request.incident_priority} />
          </Stack>
          <Link component={RouterLink} to={`/incidents/${request.incident_id}`} sx={{ fontWeight: 600 }}>
            {`#${request.incident_id} ${request.incident_title}`}
          </Link>
          <Typography variant="body2" color="text.secondary">
            {`${request.type === 'reopen' ? 'Reopen requested' : 'Closed'} by ${request.requested_by_name} · ${formatDateTime(request.requested_at)}`}
          </Typography>
          {request.reason && (
            <Typography variant="body2" sx={{ mt: 0.5, fontStyle: 'italic' }}>{`“${request.reason}”`}</Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          <Button variant="contained" onClick={() => onDecide(request, 'approved')}>Approve</Button>
          <Button variant="outlined" color="error" onClick={() => onDecide(request, 'rejected')}>Reject</Button>
        </Stack>
      </Stack>
    </Box>
  );
}

RequestItem.propTypes = {
  request: requestShape.isRequired,
  onDecide: PropTypes.func.isRequired,
};

/**
 * Admin approvals queue: close approvals (archive a finished ticket) and
 * reopen requests from reporters, oldest first so nothing waits forever.
 * The tab is kept in the URL (?type=) so the dashboard can link straight to it.
 * @returns {JSX.Element}
 */
export default function ApprovalsPage() {
  const { notify } = useNotify();
  const [params, setParams] = useSearchParams();
  const type = params.get('type') || '';
  const page = Number(params.get('page') || 1);
  const loader = useCallback(
    () => incidentsApi.pendingRequests({ type, page, page_size: PAGE_SIZE }),
    [type, page],
  );
  const {
    data, error, loading, reload,
  } = useApiData(loader);
  // The request being decided and the decision: {request, decision}.
  const [pending, setPending] = useState(null);
  const [saving, setSaving] = useState(false);

  const handleConfirm = async ({ text }) => {
    const { request, decision } = pending;
    setSaving(true);
    try {
      await incidentsApi.decideRequest(request.incident_id, request.id, { decision, note: text || undefined });
      notify(`${REQUEST_LABELS[request.type]} ${decision} for #${request.incident_id}`);
      setPending(null);
      reload();
    } catch (err) {
      // 409: someone else decided it, or the ticket changed. Reload shows the current queue.
      notify(err.message, 'error', err.status === 409 ? { label: 'Refresh', onClick: reload } : null);
      setPending(null);
    } finally {
      setSaving(false);
    }
  };

  let content;
  if (loading && !data) content = <LoadingState label="Loading approvals…" />;
  else if (error) content = <Box sx={{ p: 2 }}><ErrorState error={error} onRetry={reload} /></Box>;
  else if (!data.items.length) content = <EmptyState title="All caught up" message="There are no requests waiting for a decision." />;
  else {
    content = (
      <Stack divider={<Divider />}>
        {data.items.map((request) => (
          <RequestItem key={request.id} request={request} onDecide={(item, decision) => setPending({ request: item, decision })} />
        ))}
      </Stack>
    );
  }

  const rejecting = pending?.decision === 'rejected';
  return (
    <Box>
      <Typography variant="h4" component="h1" sx={{ mb: 2 }}>Approvals</Typography>
      <Paper>
        <Tabs
          value={type}
          onChange={(event, value) => setParams(value ? { type: value } : {})}
          aria-label="Request type"
          sx={{ px: 1, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="All" value="" />
          <Tab label="Close approvals" value="close_approval" />
          <Tab label="Reopen requests" value="reopen" />
        </Tabs>
        {content}
        {data && data.total > PAGE_SIZE && (
          <TablePagination
            component="div"
            count={data.total}
            page={page - 1}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(event, newPage) => setParams({ ...(type ? { type } : {}), page: String(newPage + 1) })}
          />
        )}
      </Paper>

      <ActionDialog
        open={Boolean(pending)}
        title={pending ? `${rejecting ? 'Reject' : 'Approve'} ${REQUEST_LABELS[pending.request.type].toLowerCase()} for #${pending.request.incident_id}?` : ''}
        description={pending ? OUTCOMES[pending.request.type][pending.decision] : ''}
        confirmLabel={rejecting ? 'Reject' : 'Approve'}
        danger={rejecting}
        textLabel={rejecting ? 'Why? (shown on the ticket)' : 'Note (optional)'}
        textRequired={rejecting}
        submitting={saving}
        onCancel={() => setPending(null)}
        onConfirm={handleConfirm}
      />
    </Box>
  );
}
