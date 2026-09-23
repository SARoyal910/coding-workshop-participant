import PropTypes from 'prop-types';
import Chip from '@mui/material/Chip';
import { PRIORITY_COLORS, PRIORITY_LABELS } from '../constants';

/**
 * Outlined chip for an incident priority.
 * @param {{priority: string, size?: string}} props
 * @returns {JSX.Element}
 */
export default function PriorityChip({ priority, size = 'small' }) {
  return (
    <Chip
      label={PRIORITY_LABELS[priority] || priority}
      color={PRIORITY_COLORS[priority] || 'default'}
      variant="outlined"
      size={size}
    />
  );
}

PriorityChip.propTypes = {
  priority: PropTypes.string.isRequired,
  size: PropTypes.oneOf(['small', 'medium']),
};
