import { useCallback, useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';
import { useMediaQuery } from 'react-responsive';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
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
import PriorityChip from '../components/PriorityChip';
import StatusChip from '../components/StatusChip';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useAuth from '../hooks/useAuth';
import useApiData from '../hooks/useApiData';
import { incidentsApi } from '../services/api';
import {
  CATEGORY_LABELS, PRIORITY_LABELS, STATUS_LABELS, formatDateTime, formatLocation,
} from '../constants';

const PAGE_SIZES = [10, 25, 50];
const SEARCH_DELAY_MS = 400;

const incidentShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  title: PropTypes.string.isRequired,
  status: PropTypes.string.isRequired,
  priority: PropTypes.string.isRequired,
  category: PropTypes.string.isRequired,
  issue_type: PropTypes.string.isRequired,
  is_archived: PropTypes.bool,
  building_name: PropTypes.string.isRequired,
  floor_number: PropTypes.number.isRequired,
  seat_code: PropTypes.string,
  reporter_name: PropTypes.string.isRequired,
  primary_engineer_name: PropTypes.string,
  updated_at: PropTypes.string.isRequired,
});

/**
 * Desktop view: one table row per incident.
 * @param {{items: Object[], onOpen: function(number): void}} props
 * @returns {JSX.Element}
 */
function IncidentTable({ items, onOpen }) {
  return (
    <TableContainer>
      <Table size="small" aria-label="Incidents">
        <TableHead>
          <TableRow>
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
              onClick={() => onOpen(incident.id)}
              sx={{ cursor: 'pointer' }}
            >
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
                <Typography variant="caption" color="text.secondary">
                  {`by ${incident.reporter_name}`}
                </Typography>
              </TableCell>
              <TableCell><StatusChip status={incident.status} archived={incident.is_archived} /></TableCell>
              <TableCell><PriorityChip priority={incident.priority} /></TableCell>
              <TableCell>
                <Typography variant="body2">{incident.issue_type}</Typography>
                <Typography variant="caption" color="text.secondary">{CATEGORY_LABELS[incident.category]}</Typography>
              </TableCell>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatLocation(incident)}</TableCell>
              <TableCell>{incident.primary_engineer_name || <Typography variant="body2" color="text.secondary">Unassigned</Typography>}</TableCell>
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
                <StatusChip status={incident.status} archived={incident.is_archived} />
                <PriorityChip priority={incident.priority} />
              </Stack>
              <Typography sx={{ fontWeight: 600 }}>{`#${incident.id} ${incident.title}`}</Typography>
              <Typography variant="body2" color="text.secondary">
                {`${incident.issue_type} · ${formatLocation(incident)}`}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {`${incident.primary_engineer_name || 'Unassigned'} · updated ${formatDateTime(incident.updated_at)}`}
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
  const navigate = useNavigate();
  const isMobile = useMediaQuery({ maxWidth: 899 });
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('q') || '');

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

  const loader = useCallback(
    () => incidentsApi.list(Object.fromEntries(new URLSearchParams(queryString))),
    [queryString],
  );
  const {
    data, error, loading, reload,
  } = useApiData(loader);

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
        message={queryString ? 'Try clearing some filters.' : 'Nothing has been reported yet.'}
      />
    );
  } else if (isMobile) content = <IncidentCards items={data.items} />;
  else content = <IncidentTable items={data.items} onOpen={(id) => navigate(`/incidents/${id}`)} />;

  return (
    <Box>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2, gap: 2 }}>
        <Typography variant="h4" component="h1">Incidents</Typography>
        <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/incidents/new">
          Report incident
        </Button>
      </Stack>

      <Paper>
        {user.role === 'engineer' && (
          <Tabs
            value={params.get('scope') || ''}
            onChange={(event, value) => updateParams({ scope: value })}
            aria-label="Which incidents"
            sx={{ px: 1, borderBottom: 1, borderColor: 'divider' }}
          >
            <Tab label="All I can see" value="" />
            <Tab label="My tickets" value="mine" />
            <Tab label="Unassigned pool" value="pool" />
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
    </Box>
  );
}
