import { useState } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink } from 'react-router-dom';
import { BarChart } from '@mui/x-charts/BarChart';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import PriorityChip from '../components/PriorityChip';
import StatTile from '../components/StatTile';
import useAuth from '../hooks/useAuth';
import useApiData from '../hooks/useApiData';
import { dashboardApi } from '../services/api';
import {
  CATEGORY_LABELS, PRIORITY_LABELS, SHIFT_LABELS, formatDateTime, formatHours, REFRESH_MS,
} from '../constants';

/** Bar color: slot 1 of the validated data-viz palette (passes lightness, chroma and contrast checks). */
const BAR_COLOR = '#2a78d6';
const TOP_ISSUE_TYPES = 8;

/** Loads the dashboard once; defined outside the component so it never changes. */
const loadDashboard = () => dashboardApi.get();

/**
 * A titled dashboard section. The subtitle states the business question it answers.
 * @param {{title: string, question?: string, children: React.ReactNode}} props
 * @returns {JSX.Element}
 */
function Section({ title, question, children }) {
  return (
    <Box component="section" sx={{ mb: 4 }}>
      <Typography variant="h6" component="h2">{title}</Typography>
      {question && <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{question}</Typography>}
      {children}
    </Box>
  );
}

Section.propTypes = {
  title: PropTypes.string.isRequired,
  question: PropTypes.string,
  children: PropTypes.node.isRequired,
};

/**
 * A row of stat tiles that wraps on small screens.
 * @param {{tiles: Object[]}} props
 * @returns {JSX.Element}
 */
function TileRow({ tiles }) {
  return (
    <Grid container spacing={2}>
      {tiles.map((tile) => (
        <Grid key={tile.label} size={{ xs: 6, sm: 4, md: 12 / Math.min(tiles.length, 6) }}>
          <StatTile {...tile} />
        </Grid>
      ))}
    </Grid>
  );
}

TileRow.propTypes = {
  tiles: PropTypes.arrayOf(PropTypes.shape({ label: PropTypes.string.isRequired })).isRequired,
};

/**
 * A small table. `columns` are [header, render(row)] pairs.
 * @param {{rows: Object[], columns: Array, rowKey: function, empty: string, label: string}} props
 * @returns {JSX.Element}
 */
function SimpleTable({
  rows, columns, rowKey, empty, label,
}) {
  if (!rows.length) return <Typography color="text.secondary" sx={{ p: 2 }}>{empty}</Typography>;
  return (
    <TableContainer>
      <Table size="small" aria-label={label}>
        <TableHead>
          <TableRow>{columns.map(([header]) => <TableCell key={header}>{header}</TableCell>)}</TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map(([header, render]) => <TableCell key={header}>{render(row)}</TableCell>)}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

SimpleTable.propTypes = {
  rows: PropTypes.arrayOf(PropTypes.object).isRequired,
  columns: PropTypes.arrayOf(PropTypes.array).isRequired,
  rowKey: PropTypes.func.isRequired,
  empty: PropTypes.string.isRequired,
  label: PropTypes.string.isRequired,
};

/**
 * Most common issue types as a horizontal bar chart (one series, so no legend),
 * with a table view of the same data for accessibility.
 * @param {{issueTypes: Object[], categories: Object[]}} props
 * @returns {JSX.Element}
 */
function IssueTypesChart({ issueTypes, categories }) {
  const [view, setView] = useState('chart');
  const top = issueTypes.slice(0, TOP_ISSUE_TYPES);
  // Leave room past the longest bar so its value label isn't clipped.
  const axisMax = Math.max(1, ...top.map((row) => row.count)) + 1;

  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1, gap: 1, flexWrap: 'wrap' }}>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
          {categories.map((row) => (
            <Chip key={row.category} size="small" variant="outlined" label={`${CATEGORY_LABELS[row.category]}: ${row.count}`} />
          ))}
        </Stack>
        <ToggleButtonGroup size="small" exclusive value={view} onChange={(event, value) => value && setView(value)} aria-label="View">
          <ToggleButton value="chart">Chart</ToggleButton>
          <ToggleButton value="table">Table</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      {view === 'chart' ? (
        <BarChart
          layout="horizontal"
          height={Math.max(220, top.length * 36)}
          dataset={top}
          yAxis={[{ scaleType: 'band', dataKey: 'issue_type', width: 130 }]}
          xAxis={[{ label: 'Incidents', tickMinStep: 1, max: axisMax }]}
          series={[{
            dataKey: 'count', label: 'Incidents', color: BAR_COLOR, barLabel: 'value', barLabelPlacement: 'outside',
          }]}
          borderRadius={4}
          grid={{ vertical: true }}
          hideLegend
        />
      ) : (
        <SimpleTable
          label="Incidents by issue type"
          rows={issueTypes}
          rowKey={(row) => row.issue_type}
          empty="No incidents in this period."
          columns={[
            ['Issue type', (row) => row.issue_type],
            ['Category', (row) => CATEGORY_LABELS[row.category]],
            ['Incidents', (row) => row.count],
            ['Avg hours logged', (row) => Number(row.avg_hours).toFixed(2)],
          ]}
        />
      )}
    </Paper>
  );
}

IssueTypesChart.propTypes = {
  issueTypes: PropTypes.arrayOf(PropTypes.shape({
    issue_type: PropTypes.string.isRequired,
    category: PropTypes.string.isRequired,
    count: PropTypes.number.isRequired,
  })).isRequired,
  categories: PropTypes.arrayOf(PropTypes.shape({
    category: PropTypes.string.isRequired,
    count: PropTypes.number.isRequired,
  })).isRequired,
};

/** Link to one incident, used inside tables. */
function IncidentLink({ id, title }) {
  return <Link component={RouterLink} to={`/incidents/${id}`}>{`#${id} ${title}`}</Link>;
}

IncidentLink.propTypes = {
  id: PropTypes.number.isRequired,
  title: PropTypes.string.isRequired,
};

/**
 * Supervisor view: one section per business question.
 * @param {{data: Object}} props
 * @returns {JSX.Element}
 */
function AdminDashboard({ data }) {
  const counts = data.status_counts;
  const times = data.response_times;
  const comms = data.communication;
  const days = `last ${data.window_days} days`;
  const { recurring } = data;

  return (
    <>
      <Section title="Open incidents" question="What incidents are currently open, and what is their status?">
        <TileRow tiles={[
          { label: 'Open', value: counts.open, to: '/incidents?status=open' },
          { label: 'In progress', value: counts.in_progress, to: '/incidents?status=in_progress' },
          {
            label: 'Blocked', value: counts.blocked, to: '/incidents?status=blocked', tone: counts.blocked ? 'error.main' : undefined,
          },
          { label: 'Resolved', value: counts.resolved, to: '/incidents?status=resolved' },
          {
            label: 'Awaiting approval', value: data.pending_requests.close_approval, caption: 'Close requests', to: '/approvals?type=close_approval',
          },
          {
            label: 'Reopen requests', value: data.pending_requests.reopen, caption: 'Pending decision', to: '/approvals?type=reopen',
          },
        ]}
        />
      </Section>

      <Section title="Needs attention" question="Which incidents are escalated or blocked, and why?">
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Paper>
              <Typography variant="subtitle2" sx={{ p: 2, pb: 0 }}>Blocked</Typography>
              <SimpleTable
                label="Blocked incidents"
                rows={data.needs_attention.blocked}
                rowKey={(row) => row.id}
                empty="Nothing is blocked."
                columns={[
                  ['Incident', (row) => <IncidentLink id={row.id} title={row.title} />],
                  ['Priority', (row) => <PriorityChip priority={row.priority} />],
                  ['Reason', (row) => row.blocked_reason],
                  ['Since', (row) => formatDateTime(row.blocked_at)],
                ]}
              />
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Paper>
              <Typography variant="subtitle2" sx={{ p: 2, pb: 0 }}>Priority raised by the reporter</Typography>
              <SimpleTable
                label="Escalated incidents"
                rows={data.needs_attention.escalated}
                rowKey={(row) => row.id}
                empty="No escalations."
                columns={[
                  ['Incident', (row) => <IncidentLink id={row.id} title={row.title} />],
                  ['Change', (row) => `${PRIORITY_LABELS[row.from_value]} → ${PRIORITY_LABELS[row.to_value]}`],
                  ['Why', (row) => row.reason],
                ]}
              />
            </Paper>
          </Grid>
        </Grid>
      </Section>

      <Section title="Recurring issues" question={`Which buildings, floors and seats have the most recurring issues? (${recurring.threshold}+ of the same issue in ${recurring.window_days} days)`}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper>
              <Typography variant="subtitle2" sx={{ p: 2, pb: 0 }}>Seats</Typography>
              <SimpleTable
                label="Recurring issues by seat"
                rows={recurring.seats}
                rowKey={(row) => `${row.seat_code}-${row.issue_type}`}
                empty="No recurring seat issues."
                columns={[
                  ['Seat', (row) => `${row.seat_code} (${row.building_name}, floor ${row.floor_number})`],
                  ['Issue', (row) => row.issue_type],
                  ['Incidents', (row) => <Chip size="small" color="warning" icon={<WarningAmberIcon />} label={row.count} />],
                ]}
              />
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper>
              <Typography variant="subtitle2" sx={{ p: 2, pb: 0 }}>Floors (across several seats)</Typography>
              <SimpleTable
                label="Recurring issues by floor"
                rows={recurring.floors}
                rowKey={(row) => `${row.building_name}-${row.floor_number}-${row.issue_type}`}
                empty="No recurring floor issues."
                columns={[
                  ['Floor', (row) => `${row.building_name}, floor ${row.floor_number}`],
                  ['Issue', (row) => row.issue_type],
                  ['Incidents', (row) => <Chip size="small" color="warning" icon={<WarningAmberIcon />} label={`${row.count} on ${row.seats} ${row.seats === 1 ? 'seat' : 'seats'}`} />],
                ]}
              />
            </Paper>
          </Grid>
          <Grid size={12}>
            <Paper>
              <Typography variant="subtitle2" sx={{ p: 2, pb: 0 }}>{`Buildings (${days})`}</Typography>
              <SimpleTable
                label="Incidents by building"
                rows={recurring.buildings}
                rowKey={(row) => row.building_name}
                empty="No incidents."
                columns={[
                  ['Building', (row) => row.building_name],
                  ['Reported', (row) => row.count],
                  ['Still active', (row) => row.active],
                ]}
              />
            </Paper>
          </Grid>
        </Grid>
      </Section>

      <Section title="Response times" question={`How quickly are incidents acknowledged, assigned and resolved? (average from report, ${days})`}>
        <TileRow tiles={[
          { label: 'Time to acknowledge', value: formatHours(times.acknowledge_hours) },
          { label: 'Time to assign', value: formatHours(times.assign_hours) },
          { label: 'Time to resolve', value: formatHours(times.resolve_hours), caption: `${times.resolved} of ${times.reported} resolved` },
        ]}
        />
      </Section>

      <Section title="Engineers" question="Which engineers are available, and how is work distributed across them?">
        <Box sx={{ mb: 2 }}>
          <TileRow tiles={data.shift_coverage.map((shift) => ({
            label: `${SHIFT_LABELS[shift.shift]}${shift.is_current ? ' · on now' : ''}`,
            value: `${shift.available}/${shift.engineers}`,
            caption: `available · ${shift.active_primary} active tickets · ${shift.missed_shifts} missed`,
            tone: shift.engineers && !shift.available ? 'error.main' : undefined,
          }))}
          />
        </Box>
        <Paper>
          <SimpleTable
            label="Engineer workload"
            rows={data.engineers}
            rowKey={(row) => row.id}
            empty="No engineers yet."
            columns={[
              ['Engineer', (row) => (
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{row.name}</Typography>
                  <Typography variant="caption" color="text.secondary">{`${CATEGORY_LABELS[row.specialty]} · ${SHIFT_LABELS[row.shift]}`}</Typography>
                </Box>
              )],
              ['Status', (row) => (
                <Stack direction="row" spacing={0.5}>
                  <Chip size="small" color={row.is_available ? 'success' : 'default'} label={row.is_available ? 'Available' : 'Unavailable'} />
                  {row.on_shift_now && <Chip size="small" color="info" variant="outlined" label="On shift now" />}
                  {row.needs_reassignment && <Chip size="small" color="warning" label="Needs reassignment" />}
                </Stack>
              )],
              ['Active (primary)', (row) => row.active_primary],
              ['Helping', (row) => row.active_helper],
              ['Helped others', (row) => row.helped_others],
              [`Hours (${data.window_days}d)`, (row) => Number(row.hours_logged).toFixed(2)],
              ['Missed shift commitments', (row) => (
                row.missed_shifts
                  ? <Chip size="small" color="error" icon={<WarningAmberIcon />} label={row.missed_shifts} />
                  : 0
              )],
            ]}
          />
        </Paper>
      </Section>

      <Section title="Most common issues" question={`What are the most common facility and technology issue categories? (${days})`}>
        <IssueTypesChart issueTypes={data.issue_types} categories={data.categories} />
      </Section>

      <Section title="Keeping employees informed" question={`How effectively are employees informed about ticket progress and outcomes? (${days})`}>
        <TileRow tiles={[
          { label: 'Time to first engineer update', value: formatHours(comms.first_update_hours) },
          {
            label: 'Resolved with an engineer note',
            value: comms.resolved_with_note_pct === null ? null : `${comms.resolved_with_note_pct}%`,
            caption: 'A resolution note is required to resolve',
          },
          {
            label: 'Reopen rate',
            value: comms.reopen_rate_pct === null ? null : `${comms.reopen_rate_pct}%`,
            caption: `of ${comms.resolved} resolved tickets`,
          },
        ]}
        />
      </Section>
    </>
  );
}

AdminDashboard.propTypes = {
  data: PropTypes.object.isRequired,
};

/**
 * Engineer view: own workload, the pool of unassigned tickets, shift record.
 * @param {{data: Object}} props
 * @returns {JSX.Element}
 */
function EngineerDashboard({ data }) {
  const counts = data.status_counts;
  const me = data.me || {};
  return (
    <>
      <Section title="My tickets">
        <TileRow tiles={[
          { label: 'In progress', value: counts.in_progress, to: '/incidents?scope=mine&status=in_progress' },
          {
            label: 'Blocked', value: counts.blocked, to: '/incidents?scope=mine&status=blocked', tone: counts.blocked ? 'error.main' : undefined,
          },
          { label: 'Resolved', value: counts.resolved, to: '/incidents?scope=mine&status=resolved' },
          { label: 'Unassigned pool', value: data.unassigned_pool, caption: 'Tickets nobody has picked up', to: '/incidents?scope=pool' },
        ]}
        />
      </Section>
      <Section title={`My last ${data.window_days} days`}>
        <TileRow tiles={[
          { label: 'My shift', value: me.on_shift_now ? 'On now' : 'Off shift', caption: SHIFT_LABELS[me.shift] },
          { label: 'Hours logged', value: Number(me.hours_logged || 0).toFixed(2) },
          { label: 'Tickets helped on', value: me.helped_others },
          {
            label: 'Missed shift commitments', value: me.missed_shifts, tone: me.missed_shifts ? 'error.main' : undefined, caption: 'Acknowledged but not resolved or blocked before shift end',
          },
        ]}
        />
      </Section>
      <Button variant="contained" component={RouterLink} to="/incidents?scope=mine">View my tickets</Button>
    </>
  );
}

EngineerDashboard.propTypes = {
  data: PropTypes.object.isRequired,
};

/**
 * Employee view: the status of the tickets they reported.
 * @param {{data: Object}} props
 * @returns {JSX.Element}
 */
function EmployeeDashboard({ data }) {
  const counts = data.status_counts;
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  if (!total) {
    return (
      <EmptyState
        title="You haven't reported anything yet"
        message="If something is broken, let us know and an engineer will pick it up."
        action={<Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/incidents/new">Report incident</Button>}
      />
    );
  }
  return (
    <>
      <Section title="My reported incidents">
        <TileRow tiles={[
          { label: 'Open', value: counts.open, to: '/incidents?status=open' },
          { label: 'In progress', value: counts.in_progress, to: '/incidents?status=in_progress' },
          { label: 'Blocked', value: counts.blocked, to: '/incidents?status=blocked' },
          {
            label: 'Resolved', value: counts.resolved, caption: 'Fixed; the engineer will close it', to: '/incidents?status=resolved', tone: counts.resolved ? 'success.main' : undefined,
          },
        ]}
        />
      </Section>
      <Stack direction="row" spacing={1.5}>
        <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/incidents/new">Report incident</Button>
        <Button variant="outlined" component={RouterLink} to="/incidents">View my incidents</Button>
      </Stack>
    </>
  );
}

EmployeeDashboard.propTypes = {
  data: PropTypes.object.isRequired,
};

const VIEWS = { admin: AdminDashboard, engineer: EngineerDashboard, employee: EmployeeDashboard };

/**
 * Role-specific dashboard: supervisors see the business metrics, engineers
 * their workload, employees the status of what they reported.
 * @returns {JSX.Element}
 */
export default function DashboardPage() {
  const { user } = useAuth();
  const {
    data, error, loading, reload,
  } = useApiData(loadDashboard, { refreshMs: REFRESH_MS });
  const View = VIEWS[user.role] || EmployeeDashboard;

  return (
    <Box sx={{ maxWidth: 1300 }}>
      <Typography variant="h4" component="h1">{`Welcome, ${user.name.split(' ')[0]}`}</Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        {user.role === 'admin' ? 'Facility and technology incidents across ACME.' : "Here's where things stand."}
      </Typography>
      {loading && !data && <LoadingState label="Loading dashboard…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && <View data={data} />}
    </Box>
  );
}
