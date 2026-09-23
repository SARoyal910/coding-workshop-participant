import { useCallback } from 'react';
import PropTypes from 'prop-types';
import { Link as RouterLink } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import useApiData from '../hooks/useApiData';
import { incidentsApi } from '../services/api';
import { STATUS_LABELS } from '../constants';

/**
 * On the report form: warns when the same issue is already open at the chosen
 * place (a likely duplicate), and when the place has a recurring pattern.
 * It only advises; the user can still submit. Shows nothing until an issue
 * type and floor are chosen, and stays quiet if the check fails.
 * @param {{issueType: string, floorId: (string|number), seatId?: (string|number)}} props
 * @returns {JSX.Element|null}
 */
export default function SimilarIncidentsWarning({ issueType, floorId, seatId = '' }) {
  const ready = Boolean(issueType && floorId);
  const loader = useCallback(
    () => (ready
      ? incidentsApi.similar({ issue_type: issueType, floor_id: floorId, seat_id: seatId })
      : Promise.resolve(null)),
    [ready, issueType, floorId, seatId],
  );
  const { data } = useApiData(loader);
  if (!ready || !data || (!data.open_count && !data.recurring)) return null;

  const place = seatId ? 'at this seat' : 'on this floor';
  const others = data.open_count - data.items.length;
  return (
    <Stack spacing={1.5} aria-live="polite">
      {data.open_count > 0 && (
        <Alert severity="info">
          <AlertTitle>{`${issueType} is already reported ${place}`}</AlertTitle>
          {`${data.open_count} open report${data.open_count === 1 ? '' : 's'}. `}
          {data.items.length > 0 && (
            <>
              {'See '}
              {data.items.map((item, index) => (
                <span key={item.id}>
                  {index > 0 && ', '}
                  <Link component={RouterLink} to={`/incidents/${item.id}`}>{`#${item.id} ${item.title}`}</Link>
                  {` (${STATUS_LABELS[item.status]})`}
                </span>
              ))}
              {others > 0 ? ` and ${others} more. ` : '. '}
            </>
          )}
          If this is the same problem, you can add a note there instead. You can still report it.
        </Alert>
      )}
      {data.recurring && (
        <Alert severity="warning">
          {`This keeps happening: ${data.recurring.count} ${issueType} incidents ${data.recurring.level === 'seat' ? 'at this seat' : 'on this floor'} in the last ${data.recurring.window_days} days. Supervisors see it flagged as a recurring issue.`}
        </Alert>
      )}
    </Stack>
  );
}

SimilarIncidentsWarning.propTypes = {
  issueType: PropTypes.string.isRequired,
  floorId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  seatId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
};
