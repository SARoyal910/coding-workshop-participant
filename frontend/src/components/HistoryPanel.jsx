import PropTypes from 'prop-types';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { EVENT_LABELS, PRIORITY_LABELS, STATUS_LABELS, formatDateTime } from '../constants';

/** Show status/priority values with their labels; other values as-is. */
function displayValue(value) {
  return STATUS_LABELS[value] || PRIORITY_LABELS[value] || value;
}

/** Event types whose from/to values are long text (shown as a quote, not "A → B"). */
const TEXT_EVENTS = new Set(['title_changed', 'description_changed', 'note_edited']);

/**
 * Audit trail: every change to the ticket, oldest first.
 * @param {{events: Object[]}} props
 * @returns {JSX.Element}
 */
export default function HistoryPanel({ events }) {
  return (
    <Stack component="ol" spacing={0} sx={{ p: 0, m: 0 }}>
      {events.map((event) => {
        const showChange = !TEXT_EVENTS.has(event.type) && (event.from_value || event.to_value);
        return (
          <Box
            component="li"
            key={event.id}
            sx={{
              listStyle: 'none', pl: 2, pb: 2, borderLeft: 2, borderColor: 'divider', position: 'relative',
            }}
          >
            <Box sx={{
              position: 'absolute', left: -6, top: 4, width: 10, height: 10, borderRadius: '50%', bgcolor: 'primary.main',
            }}
            />
            <Typography variant="body2">
              <strong>{event.actor_name}</strong>
              {' '}
              {(EVENT_LABELS[event.type] || event.type).toLowerCase()}
              {showChange && `: ${event.from_value ? `${displayValue(event.from_value)} → ` : ''}${displayValue(event.to_value || '')}`}
            </Typography>
            {event.type === 'note_edited' && event.from_value && (
              <Typography variant="caption" color="text.secondary" component="p">
                {`Previously: "${event.from_value}"`}
              </Typography>
            )}
            {event.reason && (
              <Typography variant="body2" color="text.secondary">{`Reason: ${event.reason}`}</Typography>
            )}
            <Typography variant="caption" color="text.secondary">{formatDateTime(event.created_at)}</Typography>
          </Box>
        );
      })}
    </Stack>
  );
}

HistoryPanel.propTypes = {
  events: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.number.isRequired,
    type: PropTypes.string.isRequired,
    actor_name: PropTypes.string.isRequired,
    from_value: PropTypes.string,
    to_value: PropTypes.string,
    reason: PropTypes.string,
    created_at: PropTypes.string.isRequired,
  })).isRequired,
};
