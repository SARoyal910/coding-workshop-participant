import PropTypes from 'prop-types';
import { Link as RouterLink } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Tooltip from '@mui/material/Tooltip';
import RepeatIcon from '@mui/icons-material/Repeat';
import { STATUS_LABELS, formatDateTime } from '../constants';

const TEXT = {
  seat: 'Recurring at this seat',
  floor: 'Recurring on this floor',
};

/**
 * Marks an incident that is part of a recurring pattern: 3 or more incidents
 * of the same issue type at the same seat (or on the same floor) within 30 days.
 * Renders nothing when `level` is empty. Icon + text, so it never relies on color alone.
 * @param {{level?: 'seat'|'floor'|null, size?: 'small'|'medium'}} props
 * @returns {JSX.Element|null}
 */
export default function RecurringBadge({ level = null, size = 'small' }) {
  if (!level) return null;
  return (
    <Tooltip describeChild title="Same issue type reported 3+ times here within 30 days">
      <Chip size={size} color="warning" variant="outlined" icon={<RepeatIcon />} label={TEXT[level]} />
    </Tooltip>
  );
}

RecurringBadge.propTypes = {
  level: PropTypes.oneOf(['seat', 'floor', null]),
  size: PropTypes.oneOf(['small', 'medium']),
};

/**
 * "In progress · seat 2-R-004 · Sep 12, 4:00 AM" for one related ticket.
 * @param {Object} item
 * @param {boolean} showSeat Floor-level patterns span several seats, so say which.
 * @returns {string}
 */
function relatedDetails(item, showSeat) {
  const parts = [STATUS_LABELS[item.status] + (item.is_archived ? ' (archived)' : '')];
  if (showSeat && item.seat_code) parts.push(`seat ${item.seat_code}`);
  parts.push(formatDateTime(item.created_at));
  return parts.join(' · ');
}

/**
 * Explains a recurring pattern on the incident page. Staff also get links to
 * the related tickets; employees only see the count (the API sends no related
 * tickets to them).
 * @param {{incident: Object}} props
 * @returns {JSX.Element|null}
 */
export function RecurringAlert({ incident }) {
  const { recurring } = incident;
  if (!recurring) return null;
  const place = recurring.level === 'seat' ? `at seat ${incident.seat_code}` : `on floor ${incident.floor_number}`;
  return (
    <Alert severity="warning" icon={<RepeatIcon />} sx={{ mb: 2 }}>
      <AlertTitle>Recurring issue</AlertTitle>
      {`${recurring.count} ${incident.issue_type} incidents ${place} within ${recurring.window_days} days of this one, counting this ticket.`}
      {recurring.related.length > 0 && (
        <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
          {recurring.related.map((item) => (
            <li key={item.id}>
              <Link component={RouterLink} to={`/incidents/${item.id}`}>{`#${item.id} ${item.title}`}</Link>
              {` · ${relatedDetails(item, recurring.level === 'floor')}`}
            </li>
          ))}
        </Box>
      )}
    </Alert>
  );
}

RecurringAlert.propTypes = {
  incident: PropTypes.shape({
    issue_type: PropTypes.string.isRequired,
    seat_code: PropTypes.string,
    floor_number: PropTypes.number.isRequired,
    recurring: PropTypes.shape({
      level: PropTypes.oneOf(['seat', 'floor']).isRequired,
      count: PropTypes.number.isRequired,
      window_days: PropTypes.number.isRequired,
      related: PropTypes.arrayOf(PropTypes.shape({
        id: PropTypes.number.isRequired,
        title: PropTypes.string.isRequired,
        status: PropTypes.string.isRequired,
        is_archived: PropTypes.bool,
        seat_code: PropTypes.string,
        created_at: PropTypes.string.isRequired,
      })).isRequired,
    }),
  }).isRequired,
};
