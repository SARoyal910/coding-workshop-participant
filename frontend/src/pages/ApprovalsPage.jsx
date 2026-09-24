import { useCallback, useState } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
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
import { bulkSummary, runBulk } from '../bulk';

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
 * One pending request with a select box and Approve / Reject buttons.
 * @param {{request: Object, selected: boolean, onSelect: function(): void,
 *   onDecide: function(Object, string): void}} props
 * @returns {JSX.Element}
 */
function RequestItem({
  request, selected, onSelect, onDecide,
}) {
  return (
    <Stack direction="row" spacing={1} sx={{ p: 2, pl: 1, alignItems: 'flex-start' }}>
      <Checkbox
        checked={selected}
        onChange={onSelect}
        slotProps={{ input: { 'aria-label': `Select request for #${request.incident_id}` } }}
      />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ flexGrow: 1, minWidth: 0, justifyContent: 'space-between', alignItems: { md: 'center' } }}>
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
    </Stack>
  );
}

RequestItem.propTypes = {
  request: requestShape.isRequired,
  selected: PropTypes.bool.isRequired,
  onSelect: PropTypes.func.isRequired,
  onDecide: PropTypes.func.isRequired,
};

/**
 * What the confirmation dialog says for one or several requests.
 * @param {Object[]} requests
 * @param {string} decision "approved" or "rejected"
 * @returns {{title: string, description: string}}
 */
function describeDecision(requests, decision) {
  const verb = decision === 'rejected' ? 'Reject' : 'Approve';
  const types = new Set(requests.map((request) => request.type));
  if (requests.length === 1) {
    const [request] = requests;
    return {
      title: `${verb} ${REQUEST_LABELS[request.type].toLowerCase()} for #${request.incident_id}?`,
      description: OUTCOMES[request.type][decision],
    };
  }
  return {
    title: `${verb} ${requests.length} requests?`,
    description: types.size === 1
      ? OUTCOMES[[...types][0]][decision]
      : 'Each ticket follows its own request type: see the outcome on each ticket afterwards.',
  };
}

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
  // The requests being decided and the decision: {requests, decision}.
  const [pending, setPending] = useState(null);
  const [saving, setSaving] = useState(false);
  // Selected request ids. Ids no longer on the page (decided, or another page) are ignored.
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const items = data?.items || [];
  const selected = items.filter((request) => selectedIds.has(request.id));

  const toggle = (id) => setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const toggleAll = () => setSelectedIds(
    selected.length === items.length ? new Set() : new Set(items.map((request) => request.id)),
  );

  const handleConfirm = async ({ text }) => {
    const { requests, decision } = pending;
    setSaving(true);
    // A 409 means someone else decided it or the ticket changed; the reload shows the current queue.
    const result = await runBulk(requests, (request) => incidentsApi.decideRequest(
      request.incident_id,
      request.id,
      { decision, note: text || undefined },
    ));
    const { text: message, severity } = bulkSummary(
      decision === 'rejected' ? 'Rejected requests on' : 'Approved requests on',
      result,
      (request) => `#${request.incident_id}`,
    );
    notify(message, severity);
    setSaving(false);
    setPending(null);
    setSelectedIds(new Set());
    reload();
  };

  let content;
  if (loading && !data) content = <LoadingState label="Loading approvals…" />;
  else if (error) content = <Box sx={{ p: 2 }}><ErrorState error={error} onRetry={reload} /></Box>;
  else if (!data.items.length) content = <EmptyState title="All caught up" message="There are no requests waiting for a decision." />;
  else {
    content = (
      <>
        <Stack direction="row" spacing={1} sx={{ px: 1, py: 1, alignItems: 'center', flexWrap: 'wrap', gap: 1, bgcolor: selected.length ? 'action.selected' : undefined }}>
          <Checkbox
            checked={selected.length === items.length}
            indeterminate={selected.length > 0 && selected.length < items.length}
            onChange={toggleAll}
            slotProps={{ input: { 'aria-label': 'Select all requests on this page' } }}
          />
          <Typography variant="body2" sx={{ flexGrow: 1 }}>
            {selected.length ? `${selected.length} selected` : 'Select requests to decide several at once'}
          </Typography>
          {selected.length > 0 && (
            <>
              <Button variant="contained" size="small" onClick={() => setPending({ requests: selected, decision: 'approved' })}>
                {`Approve ${selected.length}`}
              </Button>
              <Button variant="outlined" color="error" size="small" onClick={() => setPending({ requests: selected, decision: 'rejected' })}>
                {`Reject ${selected.length}`}
              </Button>
            </>
          )}
        </Stack>
        <Divider />
        <Stack divider={<Divider />}>
          {items.map((request) => (
            <RequestItem
              key={request.id}
              request={request}
              selected={selectedIds.has(request.id)}
              onSelect={() => toggle(request.id)}
              onDecide={(item, decision) => setPending({ requests: [item], decision })}
            />
          ))}
        </Stack>
      </>
    );
  }

  const rejecting = pending?.decision === 'rejected';
  const dialogText = pending ? describeDecision(pending.requests, pending.decision) : { title: '', description: '' };
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
        title={dialogText.title}
        description={dialogText.description}
        confirmLabel={rejecting ? 'Reject' : 'Approve'}
        danger={rejecting}
        textLabel={rejecting ? 'Why? (shown on each ticket)' : 'Note (optional)'}
        textRequired={rejecting}
        submitting={saving}
        onCancel={() => setPending(null)}
        onConfirm={handleConfirm}
      />
    </Box>
  );
}
