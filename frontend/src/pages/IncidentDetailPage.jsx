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
import HistoryPanel from '../components/HistoryPanel';
import NotesPanel from '../components/NotesPanel';
import { ErrorState, LoadingState } from '../components/PageState';
import PriorityChip from '../components/PriorityChip';
import StatusChip from '../components/StatusChip';
import TransitionDialog from '../components/TransitionDialog';
import WorkflowStepper from '../components/WorkflowStepper';
import useAuth from '../hooks/useAuth';
import useNotify from '../hooks/useNotify';
import useApiData from '../hooks/useApiData';
import { incidentsApi } from '../services/api';
import {
  CATEGORY_LABELS, TRANSITION_LABELS, formatDateTime, formatLocation,
} from '../constants';

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

  /** Show an API error; conflicts (409) get a Refresh action (DESIGN.md 13.8). */
  const showError = useCallback((err) => {
    const action = err.status === 409 ? { label: 'Refresh', onClick: reload } : null;
    notify(err.message, 'error', action);
  }, [notify, reload]);

  if (loading && !incident) return <LoadingState label="Loading incident…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const actions = incident.allowed_actions;
  const readOnly = incident.is_archived || incident.is_voided;
  const engineers = incident.engineers.map((engineer) => `${engineer.name}${engineer.role === 'helper' ? ' (helper)' : ''}`);

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
          </Stack>
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
      {incident.status === 'blocked' && incident.blocked_reason && (
        <Alert severity="error" sx={{ mb: 2 }}>{`Blocked: ${incident.blocked_reason}`}</Alert>
      )}
      {incident.status === 'closed' && !incident.is_archived && (
        <Alert severity="info" sx={{ mb: 2 }}>Closed by the reporter. Waiting for admin approval.</Alert>
      )}

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
              <Tab label="History" value="history" />
            </Tabs>
            <Box sx={{ p: { xs: 2, sm: 3 } }}>
              {tab === 'notes' ? (
                <NotesPanel
                  notes={incident.notes}
                  currentUserId={user.id}
                  canAdd={actions.can_add_note && !readOnly}
                  onAdd={addNote}
                  onEdit={editNote}
                />
              ) : (
                <HistoryPanel events={incident.events} />
              )}
            </Box>
          </Paper>
        </Grid>
      </Grid>

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
