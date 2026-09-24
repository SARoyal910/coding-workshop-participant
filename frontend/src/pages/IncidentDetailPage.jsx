import { useCallback, useState } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink, useParams } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import ActionDialog from '../components/ActionDialog';
import HistoryPanel from '../components/HistoryPanel';
import NotesPanel from '../components/NotesPanel';
import { ErrorState, LoadingState } from '../components/PageState';
import PriorityChip from '../components/PriorityChip';
import RecurringBadge, { RecurringAlert } from '../components/RecurringBadge';
import RequestsPanel from '../components/RequestsPanel';
import StatusChip from '../components/StatusChip';
import TransitionDialog from '../components/TransitionDialog';
import WorkflowStepper from '../components/WorkflowStepper';
import WorkLogPanel from '../components/WorkLogPanel';
import useAuth from '../hooks/useAuth';
import useNotify from '../hooks/useNotify';
import useApiData from '../hooks/useApiData';
import { incidentsApi } from '../services/api';
import {
  CATEGORY_LABELS, PRIORITY_LABELS, REQUEST_LABELS, STATUS_LABELS, TRANSITION_LABELS, formatDateTime, formatLocation,
  formatStatusAge,
} from '../constants';

const PRIORITY_CHOICES = Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ value, label }));

/**
 * Label/value pair in the details grid.
 * @param {{label: string, children: React.ReactNode}} props
 * @returns {JSX.Element}
 */
function Detail({ label, children }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="p">{label}</Typography>
      <Typography variant="body2" component="div">{children}</Typography>
    </Box>
  );
}

Detail.propTypes = {
  label: PropTypes.string.isRequired,
  children: PropTypes.node.isRequired,
};

/**
 * One incident: progress stepper, details, the actions this user may take
 * (from the API's allowed_actions), and Notes / History tabs.
 * @returns {JSX.Element}
 */
export default function IncidentDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { notify } = useNotify();
  const loader = useCallback(() => incidentsApi.get(id), [id]);
  const {
    data: incident, error, loading, reload, setData,
  } = useApiData(loader);
  const [tab, setTab] = useState('notes');
  const [target, setTarget] = useState(null);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null);
  // Which action dialog is open: 'priority' | 'reopen' | 'void' | 'decide', and the request being decided.
  const [dialog, setDialog] = useState(null);
  const [decision, setDecision] = useState(null);

  /** Show an API error; conflicts (409) get a Refresh action (DESIGN.md 13.8). */
  const showError = useCallback((err) => {
    const action = err.status === 409 ? { label: 'Refresh', onClick: reload } : null;
    notify(err.message, 'error', action);
  }, [notify, reload]);

  if (loading && !incident) return <LoadingState label="Loading incident…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const actions = incident.allowed_actions;
  const readOnly = incident.is_archived || incident.is_voided;
  const engineers = incident.engineers.map((engineer) => `${engineer.name} (${engineer.role})`);
  /**
   * After joining, say which role the server gave us. If another engineer took
   * the ticket a moment before us, we were added as a helper instead.
   * @param {Object} updated
   * @returns {string}
   */
  const joinMessage = (updated) => {
    const me = updated.engineers.find((engineer) => engineer.id === user.id);
    if (me?.role === 'primary') return 'You took this ticket. You are the primary engineer.';
    if (!incident.engineers.length) return 'Another engineer took this ticket just before you, so you joined as a helper.';
    return 'You joined as a helper';
  };
  const myAck = incident.acks.find(
    (ack) => ack.engineer_id === user.id && new Date(ack.shift_ends_at) > new Date(),
  );

  /**
   * Run an action that returns the updated incident, then show a message.
   * @param {function(): Promise<Object|null>} call
   * @param {string|function(Object): string} message Text, or built from the updated incident.
   */
  const runAction = async (call, message) => {
    setSaving(true);
    try {
      const updated = await call();
      if (updated) setData(updated); else reload();
      notify(typeof message === 'function' ? message(updated) : message);
      setDialog(null);
      setDecision(null);
    } catch (err) {
      showError(err);
      if (err.status === 409) { setDialog(null); setDecision(null); }
    } finally {
      setSaving(false);
    }
  };

  /** Save a work log; returns true, or field errors for the form. */
  const saveWorkLog = async (call, message) => {
    try {
      setData(await call());
      notify(message);
      return true;
    } catch (err) {
      showError(err);
      return err.details && Object.keys(err.details).length ? err.details : false;
    }
  };

  const changeStatus = async (extra) => {
    setSaving(true);
    try {
      const updated = await incidentsApi.changeStatus(incident.id, {
        status: target, version: incident.version, ...extra,
      });
      setData(updated);
      notify(target === 'closed' ? 'Ticket closed; waiting for admin approval' : 'Status updated');
      setTarget(null);
    } catch (err) {
      showError(err);
      if (err.status === 409) setTarget(null);
    } finally {
      setSaving(false);
    }
  };

  const saveDetails = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      setData(await incidentsApi.update(incident.id, { version: incident.version, ...editing }));
      notify('Ticket updated');
      setEditing(null);
    } catch (err) {
      showError(err);
    } finally {
      setSaving(false);
    }
  };

  const addNote = async (body) => {
    try {
      await incidentsApi.addNote(incident.id, body);
      notify('Note added');
      reload();
      return true;
    } catch (err) {
      showError(err);
      return false;
    }
  };

  const editNote = async (noteId, body) => {
    try {
      await incidentsApi.editNote(incident.id, noteId, body);
      notify('Note updated');
      reload();
      return true;
    } catch (err) {
      showError(err);
      return false;
    }
  };

  return (
    <Box sx={{ maxWidth: 1100 }}>
      <Button component={RouterLink} to="/incidents" startIcon={<ArrowBackIcon />} sx={{ mb: 1 }}>
        All incidents
      </Button>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', mb: 2 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="overline" color="text.secondary">{`Incident #${incident.id}`}</Typography>
          <Typography variant="h5" component="h1" sx={{ wordBreak: 'break-word' }}>{incident.title}</Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <StatusChip status={incident.status} archived={incident.is_archived} size="medium" />
            <PriorityChip priority={incident.priority} size="medium" />
            <RecurringBadge level={incident.recurring?.level} size="medium" />
          </Stack>
          {!readOnly && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {`${STATUS_LABELS[incident.status]} for ${formatStatusAge(incident.status_since)}`}
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', flexWrap: 'wrap', gap: 1 }}>
          {actions.can_edit && (
            <Button
              variant="outlined"
              startIcon={<EditOutlinedIcon />}
              onClick={() => setEditing({ title: incident.title, description: incident.description })}
            >
              Edit
            </Button>
          )}
          {actions.can_join && (
            <Button variant="contained" color="secondary" onClick={() => runAction(() => incidentsApi.join(incident.id), joinMessage)} disabled={saving}>
              {incident.engineers.length ? 'Join as helper' : 'Take this ticket'}
            </Button>
          )}
          {actions.can_acknowledge && !myAck && (
            <Button variant="outlined" onClick={() => runAction(() => incidentsApi.acknowledge(incident.id), 'Acknowledged for your shift')} disabled={saving}>
              Acknowledge for my shift
            </Button>
          )}
          {actions.transitions.map((status) => (
            <Button
              key={status}
              variant="contained"
              color={status === 'blocked' ? 'error' : 'primary'}
              onClick={() => setTarget(status)}
            >
              {TRANSITION_LABELS[status]}
            </Button>
          ))}
          {actions.can_change_priority && (
            <Button variant="outlined" onClick={() => setDialog('priority')}>Change priority</Button>
          )}
          {actions.can_request_reopen && (
            <Button variant="outlined" onClick={() => setDialog('reopen')}>Request reopen</Button>
          )}
          {actions.can_void && (
            <Button variant="outlined" color="error" onClick={() => setDialog('void')}>Void</Button>
          )}
        </Stack>
      </Stack>

      {incident.is_voided && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {`This ticket was voided: ${incident.void_reason}. It is hidden from lists and metrics.`}
        </Alert>
      )}
      {incident.is_archived && (
        <Alert severity="info" sx={{ mb: 2 }}>This ticket is archived and read-only.</Alert>
      )}
      <RecurringAlert incident={incident} />
      {incident.status === 'blocked' && incident.blocked_reason && (
        <Alert severity="error" sx={{ mb: 2 }}>{`Blocked: ${incident.blocked_reason}`}</Alert>
      )}
      {actions.can_join && incident.engineers.length > 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {`${incident.engineers.find((engineer) => engineer.role === 'primary')?.name || 'Another engineer'} has taken this ticket. Join as a helper to add notes or log work.`}
        </Alert>
      )}
      {myAck && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {`You acknowledged this ticket for your shift, which ends ${formatDateTime(myAck.shift_ends_at)}.`}
        </Alert>
      )}
      <RequestsPanel
        requests={incident.requests}
        canDecide={actions.can_decide_requests}
        onDecide={(request, choice) => { setDecision({ request, choice }); setDialog('decide'); }}
      />

      <Paper sx={{ p: { xs: 2, sm: 3 }, mb: 2 }}>
        <WorkflowStepper status={incident.status} archived={incident.is_archived} />
      </Paper>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }} sx={{ order: { md: 2 } }}>
          <Paper sx={{ p: 2 }}>
            <Stack spacing={1.5}>
              <Detail label="Category">{`${CATEGORY_LABELS[incident.category]} · ${incident.issue_type}`}</Detail>
              <Detail label="Location">{formatLocation(incident)}</Detail>
              <Detail label="Reported by">{`${incident.reporter_name} · ${formatDateTime(incident.created_at)}`}</Detail>
              <Detail label="Engineers">{engineers.length ? engineers.join(', ') : 'Not assigned yet'}</Detail>
              {incident.acks.length > 0 && (
                <Detail label="Shift commitments">
                  {incident.acks.map((ack) => `${ack.engineer_name} until ${formatDateTime(ack.shift_ends_at)}`).join('; ')}
                </Detail>
              )}
              {incident.acknowledged_at && <Detail label="Acknowledged">{formatDateTime(incident.acknowledged_at)}</Detail>}
              {incident.resolved_at && <Detail label="Resolved">{formatDateTime(incident.resolved_at)}</Detail>}
              <Detail label="Last updated">{formatDateTime(incident.updated_at)}</Detail>
            </Stack>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Paper sx={{ p: { xs: 2, sm: 3 }, mb: 2 }}>
            <Typography variant="h6" gutterBottom>Description</Typography>
            <Typography sx={{ whiteSpace: 'pre-wrap' }}>{incident.description}</Typography>
          </Paper>

          <Paper>
            <Tabs value={tab} onChange={(event, value) => setTab(value)} sx={{ px: 1, borderBottom: 1, borderColor: 'divider' }}>
              <Tab label={`Notes (${incident.notes.length})`} value="notes" />
              <Tab label={`Work log (${incident.work_logs.length})`} value="work" />
              <Tab label="History" value="history" />
            </Tabs>
            <Box sx={{ p: { xs: 2, sm: 3 } }}>
              {tab === 'notes' && (
                <NotesPanel
                  notes={incident.notes}
                  currentUserId={user.id}
                  canAdd={actions.can_add_note && !readOnly}
                  onAdd={addNote}
                  onEdit={editNote}
                />
              )}
              {tab === 'work' && (
                <WorkLogPanel
                  logs={incident.work_logs}
                  currentUserId={user.id}
                  canLog={actions.can_log_work}
                  readOnly={readOnly}
                  onAdd={(values) => saveWorkLog(() => incidentsApi.addWorkLog(incident.id, values), 'Work logged')}
                  onEdit={(logId, values) => saveWorkLog(() => incidentsApi.editWorkLog(incident.id, logId, values), 'Work log updated')}
                />
              )}
              {tab === 'history' && <HistoryPanel events={incident.events} />}
            </Box>
          </Paper>
        </Grid>
      </Grid>

      <ActionDialog
        open={dialog === 'priority'}
        title="Change priority"
        description="The reason is shown in the ticket history and on the admin dashboard."
        choiceLabel="Priority"
        choices={PRIORITY_CHOICES}
        initialChoice={incident.priority}
        textLabel="Why?"
        textRequired
        confirmLabel="Change priority"
        submitting={saving}
        onCancel={() => setDialog(null)}
        onConfirm={({ choice, text }) => runAction(
          () => incidentsApi.changePriority(incident.id, { version: incident.version, priority: choice, reason: text }),
          'Priority updated',
        )}
      />
      <ActionDialog
        open={dialog === 'reopen'}
        title="Ask to reopen this ticket"
        description="An admin will review your request. Tell them what is still wrong."
        textLabel="What is still wrong?"
        textRequired
        confirmLabel="Send request"
        submitting={saving}
        onCancel={() => setDialog(null)}
        onConfirm={({ text }) => runAction(() => incidentsApi.requestReopen(incident.id, text), 'Reopen requested')}
      />
      <ActionDialog
        open={dialog === 'void'}
        title="Void this ticket?"
        description="Use this for duplicates or tickets raised by mistake. It disappears from lists and metrics but stays in the audit trail."
        textLabel="Reason"
        textRequired
        confirmLabel="Void ticket"
        danger
        submitting={saving}
        onCancel={() => setDialog(null)}
        onConfirm={({ text }) => runAction(
          () => incidentsApi.void(incident.id, { version: incident.version, reason: text }),
          'Ticket voided',
        )}
      />
      <ActionDialog
        open={dialog === 'decide'}
        title={decision ? `${decision.choice === 'approved' ? 'Approve' : 'Reject'} ${REQUEST_LABELS[decision.request.type].toLowerCase()} request` : ''}
        description={decision?.choice === 'approved'
          ? (decision.request.type === 'reopen' ? 'The ticket goes back to In progress.' : 'The ticket is archived and becomes read-only.')
          : 'Tell the requester why. The note is saved in the ticket history.'}
        textLabel={decision?.choice === 'rejected' ? 'Note to the requester' : undefined}
        textRequired={decision?.choice === 'rejected'}
        confirmLabel={decision?.choice === 'approved' ? 'Approve' : 'Reject'}
        danger={decision?.choice === 'rejected'}
        submitting={saving}
        onCancel={() => { setDialog(null); setDecision(null); }}
        onConfirm={({ text }) => runAction(
          () => incidentsApi.decideRequest(incident.id, decision.request.id, {
            decision: decision.choice, ...(text ? { note: text } : {}),
          }),
          decision.choice === 'approved' ? 'Request approved' : 'Request rejected',
        )}
      />

      <TransitionDialog
        target={target}
        submitting={saving}
        onCancel={() => setTarget(null)}
        onConfirm={changeStatus}
      />

      <Dialog open={Boolean(editing)} onClose={saving ? undefined : () => setEditing(null)} fullWidth maxWidth="sm">
        <form onSubmit={saveDetails}>
          <DialogTitle>Edit ticket</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField
                label="Title"
                value={editing?.title || ''}
                onChange={(event) => setEditing((current) => ({ ...current, title: event.target.value }))}
                disabled={saving}
                required
                fullWidth
                slotProps={{ htmlInput: { maxLength: 200 } }}
              />
              <TextField
                label="Description"
                value={editing?.description || ''}
                onChange={(event) => setEditing((current) => ({ ...current, description: event.target.value }))}
                disabled={saving}
                required
                fullWidth
                multiline
                minRows={4}
                slotProps={{ htmlInput: { maxLength: 5000 } }}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditing(null)} disabled={saving}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={saving || !editing?.title.trim() || !editing?.description.trim()}
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </Box>
  );
}
