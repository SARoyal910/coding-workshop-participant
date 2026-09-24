import { useCallback } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import PriorityChip from '../components/PriorityChip';
import StatusChip from '../components/StatusChip';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useApiData from '../hooks/useApiData';
import useAuth from '../hooks/useAuth';
import { dashboardApi } from '../services/api';
import { SHIFT_LABELS, formatDateTime, formatHours } from '../constants';

/**
 * How it ended: resolved late (and how late), or still not resolved.
 * @param {Object} item
 * @returns {string}
 */
function outcome(item) {
  if (item.resolved_at) {
    const late = (new Date(item.resolved_at) - new Date(item.shift_ends_at)) / 3600000;
    return `Resolved ${formatHours(late)} after the shift ended`;
  }
  return 'Not resolved yet';
}

/**
 * Every missed shift commitment with its ticket: an engineer acknowledged a
 * ticket for their shift, and the shift ended without it being resolved or
 * blocked with a reason. Same rule as the counts on the dashboards. Admins see
 * everyone (or one engineer via ?engineer_id=); engineers see their own.
 * @returns {JSX.Element}
 */
export default function MissedShiftsPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const engineerId = params.get('engineer_id') || '';
  const isAdmin = user.role === 'admin';
  const loader = useCallback(
    () => dashboardApi.missedShifts(engineerId ? { engineer_id: engineerId } : {}),
    [engineerId],
  );
  const {
    data, error, loading, reload,
  } = useApiData(loader);

  let content;
  if (loading && !data) content = <LoadingState label="Loading missed shifts…" />;
  else if (error) content = <Box sx={{ p: 2 }}><ErrorState error={error} onRetry={reload} /></Box>;
  else if (!data.items.length) {
    content = <EmptyState title="No missed shift commitments" message="Every acknowledged ticket was resolved or blocked before the shift ended." />;
  } else {
    content = (
      <TableContainer>
        <Table size="small" aria-label="Missed shift commitments">
          <TableHead>
            <TableRow>
              <TableCell>Shift ended</TableCell>
              {isAdmin && !data.engineer && <TableCell>Engineer</TableCell>}
              <TableCell>Incident</TableCell>
              <TableCell>Committed</TableCell>
              <TableCell>At shift end</TableCell>
              <TableCell>Now</TableCell>
              <TableCell>Outcome</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((item) => (
              <TableRow key={item.id} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {formatDateTime(item.shift_ends_at)}
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    {SHIFT_LABELS[item.shift]}
                  </Typography>
                </TableCell>
                {isAdmin && !data.engineer && (
                  <TableCell>
                    <Link component={RouterLink} to={`/missed-shifts?engineer_id=${item.engineer_id}`} color="inherit" underline="hover">
                      {item.engineer_name}
                    </Link>
                  </TableCell>
                )}
                <TableCell sx={{ minWidth: 200 }}>
                  <Link component={RouterLink} to={`/incidents/${item.incident_id}`} sx={{ fontWeight: 600 }}>
                    {`#${item.incident_id} ${item.incident_title}`}
                  </Link>
                  <Box sx={{ mt: 0.5 }}><PriorityChip priority={item.priority} /></Box>
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(item.acknowledged_at)}</TableCell>
                <TableCell><StatusChip status={item.status_at_shift_end} /></TableCell>
                <TableCell><StatusChip status={item.status} archived={item.is_archived} /></TableCell>
                <TableCell>
                  <Typography variant="body2" color={item.resolved_at ? 'text.primary' : 'error.main'}>{outcome(item)}</Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  }

  return (
    <Box>
      <Typography variant="h4" component="h1" gutterBottom>Missed shift commitments</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        An engineer acknowledged the ticket for their shift, and the shift ended before it was resolved or blocked with a reason.
      </Typography>
      <Paper>
        {data && (
          <Box sx={{ p: 2, pb: 1, display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {`${data.total} missed commitment${data.total === 1 ? '' : 's'}`}
            </Typography>
            {isAdmin && data.engineer && (
              <Chip
                color="primary"
                label={`Engineer: ${data.engineer.name}`}
                onDelete={() => setParams({})}
              />
            )}
          </Box>
        )}
        {content}
      </Paper>
    </Box>
  );
}
