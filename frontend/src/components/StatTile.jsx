import PropTypes from 'prop-types';
import { Link as RouterLink } from 'react-router-dom';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';

/**
 * One headline number with a label and optional context line. When `to` is
 * given, the tile links to the matching filtered list.
 * @param {{label: string, value: (number|string|null), caption?: string, to?: string, tone?: string}} props
 * @returns {JSX.Element}
 */
export default function StatTile({
  label, value, caption, to, tone = 'text.primary',
}) {
  const body = (
    <CardContent>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h4" component="p" sx={{ color: tone, my: 0.5 }}>
        {value ?? '–'}
      </Typography>
      {caption && <Typography variant="caption" color="text.secondary">{caption}</Typography>}
    </CardContent>
  );
  return (
    <Card sx={{ height: '100%' }}>
      {to ? <CardActionArea component={RouterLink} to={to} sx={{ height: '100%' }}>{body}</CardActionArea> : body}
    </Card>
  );
}

StatTile.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  caption: PropTypes.string,
  to: PropTypes.string,
  tone: PropTypes.string,
};
