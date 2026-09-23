import { useCallback, useState } from 'react';
import PropTypes from 'prop-types';
import { useMediaQuery } from 'react-responsive';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import FormDialog from '../components/FormDialog';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useApiData from '../hooks/useApiData';
import useAuth from '../hooks/useAuth';
import useNotify from '../hooks/useNotify';
import { engineersApi } from '../services/api';
import { CATEGORY_LABELS, SHIFT_LABELS } from '../constants';

const PAGE_SIZE = 25;

const PROFILE_FIELDS = [
  { name: 'specialty', label: 'Specialty', required: true, options: CATEGORY_LABELS },
  { name: 'shift', label: 'Shift', required: true, options: SHIFT_LABELS },
  { name: 'phone', label: 'Phone (optional)', maxLength: 30 },
];

const CREATE_FIELDS = [
  { name: 'name', label: 'Full name', required: true, maxLength: 100 },
  { name: 'email', label: 'Email', required: true, maxLength: 254, helperText: 'Must be an @acme.inc address' },
  { name: 'password', label: 'First password', type: 'password', required: true, helperText: 'At least 8 characters; share it with the engineer' },
  ...PROFILE_FIELDS,
];

const EDIT_FIELDS = [
  { name: 'name', label: 'Full name', required: true, maxLength: 100 },
  ...PROFILE_FIELDS,
];

const engineerShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  name: PropTypes.string.isRequired,
  email: PropTypes.string.isRequired,
  phone: PropTypes.string,
  specialty: PropTypes.string.isRequired,
  shift: PropTypes.string.isRequired,
  is_available: PropTypes.bool.isRequired,
  active_primary: PropTypes.number.isRequired,
  active_helper: PropTypes.number.isRequired,
  helped_others: PropTypes.number.isRequired,
  hours_logged: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
  missed_shifts: PropTypes.number.isRequired,
  needs_reassignment: PropTypes.bool.isRequired,
  on_shift_now: PropTypes.bool.isRequired,
});

/**
 * Availability switch, or a read-only chip for engineers looking at a colleague.
 * @param {{engineer: Object, canChange: boolean, busy: boolean, onChange: function(boolean): void}} props
 * @returns {JSX.Element}
 */
function Availability({
  engineer, canChange, busy, onChange,
}) {
  if (!canChange) {
    return <Chip size="small" color={engineer.is_available ? 'success' : 'default'} label={engineer.is_available ? 'Available' : 'Unavailable'} />;
  }
  return (
    <FormControlLabel
      control={(
        <Switch
          checked={engineer.is_available}
          onChange={(event) => onChange(event.target.checked)}
          disabled={busy}
          slotProps={{ input: { 'aria-label': `${engineer.name} available` } }}
        />
      )}
      label={engineer.is_available ? 'Available' : 'Unavailable'}
    />
  );
}

Availability.propTypes = {
  engineer: engineerShape.isRequired,
  canChange: PropTypes.bool.isRequired,
  busy: PropTypes.bool.isRequired,
  onChange: PropTypes.func.isRequired,
};

/**
 * Status chips: on shift now, needs reassignment, missed shift commitments.
 * @param {{engineer: Object}} props
 * @returns {JSX.Element|null}
 */
function Flags({ engineer }) {
  if (!engineer.on_shift_now && !engineer.needs_reassignment && !engineer.missed_shifts) return null;
  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
      {engineer.on_shift_now && <Chip size="small" color="info" variant="outlined" label="On shift now" />}
      {engineer.needs_reassignment && (
        <Tooltip title="Unavailable but still primary on active tickets">
          <Chip size="small" color="warning" icon={<WarningAmberIcon />} label="Needs reassignment" />
        </Tooltip>
      )}
      {engineer.missed_shifts > 0 && (
        <Tooltip title="Acknowledged for a shift, but not resolved or blocked before it ended (last 30 days)">
          <Chip size="small" color="error" label={`${engineer.missed_shifts} missed shift${engineer.missed_shifts === 1 ? '' : 's'}`} />
        </Tooltip>
      )}
    </Stack>
  );
}

Flags.propTypes = { engineer: engineerShape.isRequired };

/**
 * Engineers with availability and workload. Admins add and edit engineers and
 * can change anyone's availability; engineers see their colleagues and can
 * change only their own availability.
 * @returns {JSX.Element}
 */
export default function EngineersPage() {
  const { user } = useAuth();
  const { notify } = useNotify();
  const isMobile = useMediaQuery({ maxWidth: 899 });
  const isAdmin = user.role === 'admin';
  const [page, setPage] = useState(1);
  const loader = useCallback(() => engineersApi.list({ page, page_size: PAGE_SIZE }), [page]);
  const {
    data, error, loading, reload, setData,
  } = useApiData(loader);
  // Open form: {mode: 'create'} or {mode: 'edit', engineer}.
  const [form, setForm] = useState(null);
  const [busyId, setBusyId] = useState(null);

  /** Put an updated engineer back into the current page. */
  const replaceRow = (updated) => {
    setData({ ...data, items: data.items.map((item) => (item.id === updated.id ? updated : item)) });
  };

  const handleAvailability = async (engineer, isAvailable) => {
    setBusyId(engineer.id);
    try {
      const updated = await engineersApi.setAvailability(engineer.id, isAvailable);
      replaceRow(updated);
      if (updated.needs_reassignment) {
        notify(`${updated.name} is unavailable but still primary on ${updated.active_primary} active ticket(s); flagged for reassignment.`, 'info');
      } else {
        notify(`${updated.name} is now ${isAvailable ? 'available' : 'unavailable'}`);
      }
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleSave = async (body) => {
    if (form.mode === 'create') {
      const created = await engineersApi.create(body);
      notify(`${created.name} added. They can log in with the password you set.`);
      reload();
    } else {
      replaceRow(await engineersApi.update(form.engineer.id, body));
      notify('Engineer updated');
    }
    setForm(null);
  };

  const canChange = (engineer) => isAdmin || engineer.id === user.id;

  const editButton = (engineer) => isAdmin && (
    <Tooltip title={`Edit ${engineer.name}`}>
      <IconButton size="small" aria-label={`Edit ${engineer.name}`} onClick={() => setForm({ mode: 'edit', engineer })}>
        <EditOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );

  const contact = (engineer) => [engineer.email, engineer.phone].filter(Boolean).join(' · ');

  let content;
  if (loading && !data) content = <LoadingState label="Loading engineers…" />;
  else if (error) content = <Box sx={{ p: 2 }}><ErrorState error={error} onRetry={reload} /></Box>;
  else if (!data.items.length) content = <EmptyState title="No engineers yet" message={isAdmin ? 'Add the first engineer to start assigning work.' : undefined} />;
  else if (isMobile) {
    content = (
      <Stack spacing={1.5} sx={{ p: 1.5 }}>
        {data.items.map((engineer) => (
          <Card key={engineer.id}>
            <CardContent>
              <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography sx={{ fontWeight: 600 }}>{engineer.name}</Typography>
                {editButton(engineer)}
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {`${CATEGORY_LABELS[engineer.specialty]} · ${SHIFT_LABELS[engineer.shift]}`}
              </Typography>
              <Typography variant="caption" color="text.secondary">{contact(engineer)}</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                {`${engineer.active_primary} primary · ${engineer.active_helper} helping · helped ${engineer.helped_others} · ${Number(engineer.hours_logged)} h logged`}
              </Typography>
              <Availability engineer={engineer} canChange={canChange(engineer)} busy={busyId === engineer.id} onChange={(value) => handleAvailability(engineer, value)} />
              <Flags engineer={engineer} />
            </CardContent>
          </Card>
        ))}
      </Stack>
    );
  } else {
    content = (
      <TableContainer>
        <Table size="small" aria-label="Engineers">
          <TableHead>
            <TableRow>
              <TableCell>Engineer</TableCell>
              <TableCell>Specialty · shift</TableCell>
              <TableCell>Availability</TableCell>
              <TableCell align="right">Active (primary / helping)</TableCell>
              <TableCell align="right">Helped others</TableCell>
              <TableCell align="right">Hours (30 days)</TableCell>
              <TableCell>Shift and flags</TableCell>
              {isAdmin && <TableCell aria-label="Actions" />}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((engineer) => (
              <TableRow key={engineer.id} hover>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {engineer.name}
                    {engineer.id === user.id && ' (you)'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">{contact(engineer)}</Typography>
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  <Typography variant="body2">{CATEGORY_LABELS[engineer.specialty]}</Typography>
                  <Typography variant="caption" color="text.secondary">{SHIFT_LABELS[engineer.shift]}</Typography>
                </TableCell>
                <TableCell>
                  <Availability engineer={engineer} canChange={canChange(engineer)} busy={busyId === engineer.id} onChange={(value) => handleAvailability(engineer, value)} />
                </TableCell>
                <TableCell align="right">{`${engineer.active_primary} / ${engineer.active_helper}`}</TableCell>
                <TableCell align="right">{engineer.helped_others}</TableCell>
                <TableCell align="right">{Number(engineer.hours_logged)}</TableCell>
                <TableCell><Flags engineer={engineer} /></TableCell>
                {isAdmin && <TableCell>{editButton(engineer)}</TableCell>}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  }

  return (
    <Box>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2, gap: 2 }}>
        <Typography variant="h4" component="h1">Engineers</Typography>
        {isAdmin && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setForm({ mode: 'create' })}>
            Add engineer
          </Button>
        )}
      </Stack>

      <Paper>
        {content}
        {data && data.total > PAGE_SIZE && (
          <TablePagination
            component="div"
            count={data.total}
            page={page - 1}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(event, newPage) => setPage(newPage + 1)}
          />
        )}
      </Paper>

      <FormDialog
        open={Boolean(form)}
        title={form?.mode === 'edit' ? `Edit ${form.engineer.name}` : 'Add engineer'}
        submitLabel={form?.mode === 'edit' ? 'Save' : 'Add engineer'}
        fields={form?.mode === 'edit' ? EDIT_FIELDS : CREATE_FIELDS}
        initialValues={form?.mode === 'edit' ? {
          name: form.engineer.name,
          specialty: form.engineer.specialty,
          shift: form.engineer.shift,
          phone: form.engineer.phone || '',
        } : { specialty: '', shift: 'day' }}
        onCancel={() => setForm(null)}
        onSubmit={handleSave}
      />
    </Box>
  );
}
