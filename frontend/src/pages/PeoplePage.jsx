import { useCallback, useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { useSearchParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import InputAdornment from '@mui/material/InputAdornment';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import SearchIcon from '@mui/icons-material/Search';
import ActionDialog from '../components/ActionDialog';
import FormDialog from '../components/FormDialog';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useApiData from '../hooks/useApiData';
import useAuth from '../hooks/useAuth';
import useNotify from '../hooks/useNotify';
import { peopleApi } from '../services/api';
import { CATEGORY_LABELS, ROLE_LABELS, SHIFT_LABELS } from '../constants';

const PAGE_SIZE = 25;
const SEARCH_DELAY_MS = 400;
const ROLE_COLORS = { admin: 'secondary', engineer: 'primary', employee: 'default' };

const PROFILE_FIELDS = [
  { name: 'specialty', label: 'Specialty', required: true, options: CATEGORY_LABELS },
  { name: 'shift', label: 'Shift', required: true, options: SHIFT_LABELS },
];

/** What each role change means, shown in the confirmation. */
const OUTCOMES = {
  admin: 'They get full admin rights (dashboard, approvals, people, facilities) on their next click. Use this to cover an admin on vacation; you can take it back at any time.',
  engineer: 'They become an engineer on their next click and can take and work tickets.',
  employee: 'They go back to reporting and following their own tickets only.',
};

const personShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  name: PropTypes.string.isRequired,
  email: PropTypes.string.isRequired,
  role: PropTypes.oneOf(['employee', 'engineer', 'admin']).isRequired,
  specialty: PropTypes.string,
  shift: PropTypes.string,
});

/**
 * The role changes offered for one person, depending on their current role.
 * @param {{person: Object, isSelf: boolean, onChange: function(Object, string): void}} props
 * @returns {JSX.Element}
 */
function RoleActions({ person, isSelf, onChange }) {
  if (isSelf) return <Chip size="small" label="You" variant="outlined" />;
  const targets = {
    employee: ['engineer'],
    engineer: ['admin', 'employee'],
    admin: ['engineer', 'employee'],
  }[person.role];
  return (
    <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
      {targets.map((role) => (
        <Button
          key={role}
          size="small"
          variant={role === 'employee' ? 'text' : 'outlined'}
          color={role === 'employee' ? 'inherit' : 'primary'}
          onClick={() => onChange(person, role)}
        >
          {`Make ${ROLE_LABELS[role].toLowerCase()}`}
        </Button>
      ))}
    </Stack>
  );
}

RoleActions.propTypes = {
  person: personShape.isRequired,
  isSelf: PropTypes.bool.isRequired,
  onChange: PropTypes.func.isRequired,
};

/**
 * Admin-only list of everyone (admins, engineers, employees) with role changes:
 * promote an employee to engineer, make an engineer an admin (for example to
 * cover a vacation) and take it back. Changes apply on the person's next request.
 * @returns {JSX.Element}
 */
export default function PeoplePage() {
  const { user } = useAuth();
  const { notify } = useNotify();
  const [params, setParams] = useSearchParams();
  const role = params.get('role') || '';
  const page = Number(params.get('page') || 1);
  const [search, setSearch] = useState(params.get('q') || '');
  // {person, role}: the change being confirmed.
  const [pending, setPending] = useState(null);
  const [saving, setSaving] = useState(false);

  const update = useCallback((changes) => setParams((current) => {
    const next = new URLSearchParams(current);
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
    if (!('page' in changes)) next.delete('page');
    return next;
  }), [setParams]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (search.trim() !== (params.get('q') || '')) update({ q: search.trim() });
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search, params, update]);

  const loader = useCallback(() => peopleApi.list({
    page, page_size: PAGE_SIZE, ...(role ? { role } : {}), ...(params.get('q') ? { q: params.get('q') } : {}),
  }), [page, role, params]);
  const {
    data, error, loading, reload,
  } = useApiData(loader);

  const save = async (body) => {
    const { person } = pending;
    const updated = await peopleApi.changeRole(person.id, body);
    notify(`${updated.name} is now ${ROLE_LABELS[updated.role].toLowerCase()}`);
    setPending(null);
    reload();
  };

  const confirm = async () => {
    setSaving(true);
    try {
      await save({ role: pending.role });
    } catch (err) {
      notify(err.message, 'error');
      setPending(null);
    } finally {
      setSaving(false);
    }
  };

  // A new engineer with no earlier engineer profile needs a specialty and shift.
  const needsProfile = pending?.role === 'engineer' && !pending.person.specialty;

  let content;
  if (loading && !data) content = <LoadingState label="Loading people…" />;
  else if (error) content = <Box sx={{ p: 2 }}><ErrorState error={error} onRetry={reload} /></Box>;
  else if (!data.items.length) content = <EmptyState title="Nobody found" message="Try another tab or search." />;
  else {
    content = (
      <TableContainer>
        <Table size="small" aria-label="People">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Engineer profile</TableCell>
              <TableCell align="right">Change role</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((person) => (
              <TableRow key={person.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{person.name}</TableCell>
                <TableCell>{person.email}</TableCell>
                <TableCell>
                  <Chip size="small" label={ROLE_LABELS[person.role]} color={ROLE_COLORS[person.role]} />
                </TableCell>
                <TableCell>
                  {/* A profile is kept when someone is made an employee, but only matters for engineers and admins. */}
                  {person.specialty && person.role !== 'employee' ? (
                    <Typography variant="body2">
                      {`${CATEGORY_LABELS[person.specialty]} · ${person.shift} shift`}
                    </Typography>
                  ) : (
                    <Typography variant="body2" color="text.secondary">None</Typography>
                  )}
                </TableCell>
                <TableCell align="right">
                  <RoleActions
                    person={person}
                    isSelf={person.id === user.id}
                    onChange={(target, newRole) => setPending({ person: target, role: newRole })}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  }

  const title = pending ? `Make ${pending.person.name} ${ROLE_LABELS[pending.role].toLowerCase()}?` : '';
  return (
    <Box>
      <Typography variant="h4" component="h1" gutterBottom>People</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Everyone with an account. Promote employees to engineers, and give an engineer admin rights while you are away.
      </Typography>
      <Paper>
        <Tabs
          value={role}
          onChange={(event, value) => update({ role: value })}
          aria-label="Filter by role"
          sx={{ px: 1, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Everyone" value="" />
          <Tab label="Admins" value="admin" />
          <Tab label="Engineers" value="engineer" />
          <Tab label="Employees" value="employee" />
        </Tabs>
        <Box sx={{ p: 2 }}>
          <TextField
            size="small"
            label="Search"
            placeholder="Name or email"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            sx={{ width: { xs: '100%', sm: 360 } }}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }}
          />
        </Box>
        {content}
        {data && data.total > PAGE_SIZE && (
          <TablePagination
            component="div"
            count={data.total}
            page={page - 1}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(event, next) => update({ page: String(next + 1) })}
          />
        )}
      </Paper>

      <FormDialog
        open={Boolean(needsProfile)}
        title={title}
        submitLabel="Make engineer"
        fields={PROFILE_FIELDS}
        onCancel={() => setPending(null)}
        onSubmit={(values) => save({ role: 'engineer', ...values })}
      />
      <ActionDialog
        open={Boolean(pending) && !needsProfile}
        title={title}
        description={pending ? OUTCOMES[pending.role] : ''}
        confirmLabel={pending ? `Make ${ROLE_LABELS[pending.role].toLowerCase()}` : 'Confirm'}
        danger={pending?.role === 'employee'}
        submitting={saving}
        onCancel={() => setPending(null)}
        onConfirm={confirm}
      />
    </Box>
  );
}
