import { useCallback, useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';
import { useMediaQuery } from 'react-responsive';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
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
import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import ActionDialog from '../components/ActionDialog';
import PriorityChip from '../components/PriorityChip';
import RecurringBadge from '../components/RecurringBadge';
import StatusChip from '../components/StatusChip';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useAuth from '../hooks/useAuth';
import useApiData from '../hooks/useApiData';
import useNotify from '../hooks/useNotify';
import { bulkSummary, runBulk } from '../bulk';
import { incidentsApi } from '../services/api';
import {
  CATEGORY_LABELS, PRIORITY_LABELS, STATUS_LABELS, formatDateTime, formatLocation, formatStatusAge, REFRESH_MS,
} from '../constants';

const PAGE_SIZES = [10, 25, 50];
const PRIORITY_CHOICES = Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ value, label }));
const SEARCH_DELAY_MS = 400;

const incidentShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  title: PropTypes.string.isRequired,
  status: PropTypes.string.isRequired,
  priority: PropTypes.string.isRequired,
  category: PropTypes.string.isRequired,
  issue_type: PropTypes.string.isRequired,
  is_archived: PropTypes.bool,
  is_voided: PropTypes.bool,
  void_reason: PropTypes.string,
  recurring: PropTypes.oneOf(['seat', 'floor', null]),
  building_name: PropTypes.string.isRequired,
  floor_number: PropTypes.number.isRequired,
  seat_code: PropTypes.string,
  seat_count: PropTypes.number,
  reporter_name: PropTypes.string.isRequired,
  primary_engineer_name: PropTypes.string,
  updated_at: PropTypes.string.isRequired,
  version: PropTypes.number,
  status_since: PropTypes.string,
  engineer_role: PropTypes.oneOf(['primary', 'helper', null]),
});

/**
 * Desktop view: one table row per incident. With `selection`, each row gets a
 * select box for bulk actions.
 * @param {{items: Object[], onOpen: function(number): void,
 *   selection?: {ids: Set<number>, toggle: function(number): void, toggleAll: function(): void}}} props
 * @returns {JSX.Element}
 */
function IncidentTable({ items, onOpen, selection = null }) {
  const selectedCount = selection ? items.filter((incident) => selection.ids.has(incident.id)).length : 0;
  return (
    <TableContainer>
      <Table size="small" aria-label="Incidents">
        <TableHead>
          <TableRow>
            {selection && (
              <TableCell padding="checkbox">
                <Checkbox
                  checked={selectedCount === items.length}
                  indeterminate={selectedCount > 0 && selectedCount < items.length}
                  onChange={selection.toggleAll}
                  slotProps={{ input: { 'aria-label': 'Select all incidents on this page' } }}
                />
              </TableCell>
            )}
            <TableCell>#</TableCell>
            <TableCell>Title</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Priority</TableCell>
            <TableCell>Issue</TableCell>
            <TableCell>Location</TableCell>
            <TableCell>Engineer</TableCell>
            <TableCell>Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((incident) => (
            <TableRow
              key={incident.id}
              hover
              selected={Boolean(selection?.ids.has(incident.id))}
              onClick={() => onOpen(incident.id)}
              sx={{ cursor: 'pointer' }}
            >
              {selection && (
                <TableCell padding="checkbox" onClick={(event) => event.stopPropagation()}>
                  <Checkbox
                    checked={selection.ids.has(incident.id)}
                    onChange={() => selection.toggle(incident.id)}
                    slotProps={{ input: { 'aria-label': `Select incident #${incident.id}` } }}
                  />
                </TableCell>
              )}
              <TableCell>{incident.id}</TableCell>
              <TableCell sx={{ maxWidth: 260 }}>
                {/* A real link keeps rows keyboard- and screen-reader-accessible. */}
                <Typography
                  component={RouterLink}
                  to={`/incidents/${incident.id}`}
                  onClick={(event) => event.stopPropagation()}
                  variant="body2"
                  sx={{
                    display: 'block', fontWeight: 600, color: 'text.primary', textDecoration: 'none',
                  }}
                  noWrap
                >
                  {incident.title}
                </Typography>
                <Stack direction="row" sx={{ alignItems: 'center', flexWrap: 'wrap', columnGap: 1, rowGap: 0.5 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                    {`by ${incident.reporter_name}`}
                  </Typography>
                  <RecurringBadge level={incident.recurring} />
                </Stack>
              </TableCell>
              <TableCell>
                <StatusChip status={incident.status} archived={incident.is_archived} voided={incident.is_voided} />
                {!incident.is_archived && !incident.is_voided && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, whiteSpace: 'nowrap' }}>
                    {`for ${formatStatusAge(incident.status_since)}`}
                  </Typography>
                )}
                {incident.is_voided && incident.void_reason && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, maxWidth: 180 }}>
                    {incident.void_reason}
                  </Typography>
                )}
              </TableCell>
              <TableCell><PriorityChip priority={incident.priority} /></TableCell>
              <TableCell>
                <Typography variant="body2">{incident.issue_type}</Typography>
                <Typography variant="caption" color="text.secondary">{CATEGORY_LABELS[incident.category]}</Typography>
              </TableCell>
              <TableCell sx={{ minWidth: 160 }}>{formatLocation(incident)}</TableCell>
              <TableCell>
                {incident.primary_engineer_name || <Typography variant="body2" color="text.secondary">Unassigned</Typography>}
                {incident.engineer_role && (
                  <Chip
                    size="small"
                    variant="outlined"
                    color={incident.engineer_role === 'primary' ? 'primary' : 'default'}
                    label={incident.engineer_role === 'primary' ? 'Their role: primary' : 'Their role: helper'}
                    sx={{ display: 'flex', width: 'fit-content', mt: 0.5 }}
                  />
                )}
              </TableCell>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(incident.updated_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

IncidentTable.propTypes = {
  items: PropTypes.arrayOf(incidentShape).isRequired,
  onOpen: PropTypes.func.isRequired,
  selection: PropTypes.shape({
    ids: PropTypes.instanceOf(Set).isRequired,
    toggle: PropTypes.func.isRequired,
    toggleAll: PropTypes.func.isRequired,
  }),
};

/**
 * Mobile view: one card per incident.
 * @param {{items: Object[]}} props
 * @returns {JSX.Element}
 */
function IncidentCards({ items }) {
  return (
    <Stack spacing={1.5} sx={{ p: 1.5 }}>
      {items.map((incident) => (
        <Card key={incident.id}>
          <CardActionArea component={RouterLink} to={`/incidents/${incident.id}`}>
            <CardContent>
              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <StatusChip status={incident.status} archived={incident.is_archived} voided={incident.is_voided} />
                <PriorityChip priority={incident.priority} />
                <RecurringBadge level={incident.recurring} />
              </Stack>
              <Typography sx={{ fontWeight: 600 }}>{`#${incident.id} ${incident.title}`}</Typography>
              <Typography variant="body2" color="text.secondary">
                {`${incident.issue_type} · ${formatLocation(incident)}`}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {[
                  incident.primary_engineer_name || 'Unassigned',
                  incident.engineer_role && `their role: ${incident.engineer_role}`,
                  !incident.is_archived && !incident.is_voided && `${STATUS_LABELS[incident.status]} for ${formatStatusAge(incident.status_since)}`,
                  incident.is_voided && `Voided: ${incident.void_reason}`,
                  `updated ${formatDateTime(incident.updated_at)}`,
                ].filter(Boolean).join(' · ')}
              </Typography>
            </CardContent>
          </CardActionArea>
        </Card>
      ))}
    </Stack>
  );
}

IncidentCards.propTypes = {
  items: PropTypes.arrayOf(incidentShape).isRequired,
};

/**
 * Searchable, filterable, paginated incident list. Filters live in the URL so
 * a filtered view can be bookmarked or shared. Engineers get Mine / Pool tabs.
 * @returns {JSX.Element}
 */
export default function IncidentListPage() {
  const { user } = useAuth();
  const { notify } = useNotify();
  const navigate = useNavigate();
  const isMobile = useMediaQuery({ maxWidth: 899 });
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('q') || '');

  // Engineers default to "My tickets"; everyone else sees everything they're allowed to.
  const isEngineer = user.role === 'engineer';
  const scope = isEngineer ? params.get('scope') || 'mine' : null;
  const page = Number(params.get('page') || 1);
  const pageSize = Number(params.get('page_size') || 25);
  const queryString = params.toString();

  /** Change one or more URL filters; any filter change goes back to page 1. */
  const updateParams = useCallback((changes, resetPage = true) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      Object.entries(changes).forEach(([key, value]) => {
        if (value === '' || value === null || value === undefined) next.delete(key);
        else next.set(key, String(value));
      });
      if (resetPage) next.delete('page');
      return next;
    });
  }, [setParams]);

  // Apply the search box after the user stops typing.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (search.trim() !== (params.get('q') || '')) updateParams({ q: search.trim() });
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search, params, updateParams]);

  const loader = useCallback(() => {
    const query = Object.fromEntries(new URLSearchParams(queryString));
    if (scope) query.scope = scope;
    return incidentsApi.list(query);
  }, [queryString, scope]);
  // Bulk priority/void send each ticket's version; pause the background refresh while
  // their dialog is open so a refresh can't swap in newer versions (see IncidentDetailPage).
  const [bulkDialog, setBulkDialog] = useState(null);
  const {
    data, error, loading, reload,
  } = useApiData(loader, { refreshMs: bulkDialog ? 0 : REFRESH_MS });

  // Bulk actions: engineers take or join tickets, admins change priority or void.
  // Selected ids that are no longer on the page are ignored.
  const canBulk = !isMobile && (isEngineer || user.role === 'admin') && params.get('archived') !== 'true';
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkSaving, setBulkSaving] = useState(false);
  const items = data?.items || [];
  const selected = items.filter((incident) => selectedIds.has(incident.id));
  const selection = canBulk ? {
    ids: selectedIds,
    toggle: (id) => setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    }),
    toggleAll: () => setSelectedIds(
      selected.length === items.length ? new Set() : new Set(items.map((incident) => incident.id)),
    ),
  } : null;

  /** Run one call per selected ticket, report the outcome, then refresh. */
  const runBulkAction = async (verb, call) => {
    setBulkSaving(true);
    const result = await runBulk(selected, call);
    const { text, severity } = bulkSummary(verb, result, (incident) => `#${incident.id}`);
    notify(text, severity);
    setBulkSaving(false);
    setBulkDialog(null);
    setSelectedIds(new Set());
    reload();
  };

  const filterSelect = (name, label, labels) => (
    <TextField
      select
      size="small"
      label={label}
      value={params.get(name) || ''}
      onChange={(event) => updateParams({ [name]: event.target.value })}
      sx={{ minWidth: 150 }}
    >
      <MenuItem value="">All</MenuItem>
      {Object.entries(labels).map(([value, text]) => <MenuItem key={value} value={value}>{text}</MenuItem>)}
    </TextField>
  );

  let content;
  if (loading && !data) content = <LoadingState label="Loading incidents…" />;
  else if (error) content = <Box sx={{ p: 2 }}><ErrorState error={error} onRetry={reload} /></Box>;
  else if (!data.items.length) {
    content = (
      <EmptyState
        title="No incidents found"
        message={(() => {
          if (scope === 'mine' && !queryString) return "You're not on any tickets yet. Check the Unassigned tab to pick one up.";
          return queryString ? 'Try clearing some filters.' : 'Nothing has been reported yet.';
        })()}
      />
    );
  } else if (isMobile) content = <IncidentCards items={data.items} />;
  else content = <IncidentTable items={data.items} onOpen={(id) => navigate(`/incidents/${id}`)} selection={selection} />;

  return (
    <Box>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2, gap: 2 }}>
        <Typography variant="h4" component="h1">Incidents</Typography>
        <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/incidents/new">
          Report incident
        </Button>
      </Stack>

      <Paper>
        {isEngineer && (
          <Tabs
            value={scope}
            onChange={(event, value) => updateParams({ scope: value === 'mine' ? '' : value })}
            aria-label="Which incidents"
            sx={{ px: 1, borderBottom: 1, borderColor: 'divider' }}
          >
            <Tab label="My tickets" value="mine" />
            <Tab label="Unassigned" value="pool" />
            <Tab label="All active" value="all" />
          </Tabs>
        )}

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ p: 2, alignItems: { md: 'center' } }}>
          <TextField
            size="small"
            label="Search"
            placeholder="Title or description"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            sx={{ flexGrow: 1 }}
            slotProps={{
              input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> },
            }}
          />
          {filterSelect('status', 'Status', STATUS_LABELS)}
          {filterSelect('priority', 'Priority', PRIORITY_LABELS)}
          {filterSelect('category', 'Category', CATEGORY_LABELS)}
          <FormControlLabel
            control={(
              <Switch
                checked={params.get('archived') === 'true'}
                onChange={(event) => updateParams({ archived: event.target.checked ? 'true' : '' })}
              />
            )}
            label="Archived"
          />
        </Stack>

        {params.get('engineer_id') && data?.engineer && (
          <Box sx={{ px: 2, pb: 1 }}>
            <Chip
              color="primary"
              label={`Engineer: ${data.engineer.name} · ${data.total} ${params.get('archived') === 'true' ? 'archived' : 'active'} ticket${data.total === 1 ? '' : 's'}`}
              onDelete={() => updateParams({ engineer_id: '' })}
            />
          </Box>
        )}
        {params.get('pending') && (
          <Box sx={{ px: 2, pb: 1 }}>
            <Chip
              color="warning"
              label={params.get('pending') === 'reopen' ? 'Showing: reopen requests' : 'Showing: awaiting close approval'}
              onDelete={() => updateParams({ pending: '' })}
            />
          </Box>
        )}

        {selected.length > 0 && (
          <Stack
            direction="row"
            spacing={1}
            sx={{ px: 2, py: 1, alignItems: 'center', flexWrap: 'wrap', gap: 1, bgcolor: 'action.selected' }}
            role="region"
            aria-label="Bulk actions"
          >
            <Typography variant="body2" sx={{ flexGrow: 1, fontWeight: 600 }}>{`${selected.length} selected`}</Typography>
            {isEngineer && (
              <Button
                variant="contained"
                size="small"
                disabled={bulkSaving}
                onClick={() => runBulkAction('Took or joined', (incident) => incidentsApi.join(incident.id))}
              >
                Take / join selected
              </Button>
            )}
            {user.role === 'admin' && (
              <>
                <Button variant="outlined" size="small" onClick={() => setBulkDialog('priority')}>Change priority</Button>
                <Button variant="outlined" size="small" color="error" onClick={() => setBulkDialog('void')}>Void</Button>
              </>
            )}
            <Button size="small" onClick={() => setSelectedIds(new Set())}>Clear</Button>
          </Stack>
        )}

        {content}

        {data && data.total > 0 && (
          <TablePagination
            component="div"
            count={data.total}
            page={page - 1}
            rowsPerPage={pageSize}
            rowsPerPageOptions={PAGE_SIZES}
            onPageChange={(event, newPage) => updateParams({ page: newPage + 1 }, false)}
            onRowsPerPageChange={(event) => updateParams({ page_size: event.target.value })}
          />
        )}
      </Paper>

      <ActionDialog
        open={bulkDialog === 'priority'}
        title={`Change priority of ${selected.length} ${selected.length === 1 ? 'ticket' : 'tickets'}`}
        description="The same priority and reason are applied to each ticket and shown in its history."
        choiceLabel="Priority"
        choices={PRIORITY_CHOICES}
        initialChoice="high"
        textLabel="Why?"
        textRequired
        confirmLabel="Change priority"
        submitting={bulkSaving}
        onCancel={() => setBulkDialog(null)}
        onConfirm={({ choice, text }) => runBulkAction('Changed priority on', (incident) => incidentsApi.changePriority(
          incident.id,
          { version: incident.version, priority: choice, reason: text },
        ))}
      />
      <ActionDialog
        open={bulkDialog === 'void'}
        title={`Void ${selected.length} ${selected.length === 1 ? 'ticket' : 'tickets'}?`}
        description="Use this for duplicates or tickets raised by mistake. They disappear from lists and metrics but stay in the audit trail."
        textLabel="Reason"
        textRequired
        confirmLabel="Void"
        danger
        submitting={bulkSaving}
        onCancel={() => setBulkDialog(null)}
        onConfirm={({ text }) => runBulkAction('Voided', (incident) => incidentsApi.void(
          incident.id,
          { version: incident.version, reason: text },
        ))}
      />
    </Box>
  );
}
