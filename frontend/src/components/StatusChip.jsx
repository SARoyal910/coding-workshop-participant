import PropTypes from 'prop-types';
import Chip from '@mui/material/Chip';
import { STATUS_COLORS, STATUS_LABELS } from '../constants';

/**
 * Colored chip for an incident status. Archived tickets show "Archived" instead.
 * @param {{status: string, archived?: boolean, size?: string}} props
 * @returns {JSX.Element}
 */
export default function StatusChip({ status, archived = false, size = 'small' }) {
  if (archived) return <Chip label="Archived" size={size} variant="outlined" />;
  return (
    <Chip
      label={STATUS_LABELS[status] || status}
      color={STATUS_COLORS[status] || 'default'}
      size={size}
    />
  );
}

StatusChip.propTypes = {
  status: PropTypes.string.isRequired,
  archived: PropTypes.bool,
  size: PropTypes.oneOf(['small', 'medium']),
};
