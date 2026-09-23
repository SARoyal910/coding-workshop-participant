import PropTypes from 'prop-types';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import BuildCircleOutlinedIcon from '@mui/icons-material/BuildCircleOutlined';

/**
 * Centered card used by the login and register pages.
 * @param {{title: string, subtitle?: string, children: React.ReactNode}} props
 * @returns {JSX.Element}
 */
export default function AuthCard({ title, subtitle, children }) {
  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 420 }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3, color: 'primary.main' }}>
            <BuildCircleOutlinedIcon fontSize="large" aria-hidden />
            <Typography variant="h6" component="p">ACME Incidents</Typography>
          </Box>
          <Typography variant="h5" component="h1">{title}</Typography>
          {subtitle && <Typography color="text.secondary" sx={{ mt: 0.5, mb: 3 }}>{subtitle}</Typography>}
          {children}
        </CardContent>
      </Card>
    </Box>
  );
}

AuthCard.propTypes = {
  title: PropTypes.string.isRequired,
  subtitle: PropTypes.string,
  children: PropTypes.node.isRequired,
};
