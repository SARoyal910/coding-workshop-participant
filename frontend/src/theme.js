import { createTheme } from '@mui/material/styles';

/**
 * One theme for the whole app, so colors, type and spacing stay consistent.
 * Status and priority colors live in constants.js and use these palette names.
 */
const theme = createTheme({
  palette: {
    primary: { main: '#1f4e79' },
    secondary: { main: '#00897b' },
    background: { default: '#f4f6f8' },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
    MuiPaper: { defaultProps: { variant: 'outlined' } },
    MuiAppBar: { defaultProps: { elevation: 0 } },
  },
});

export default theme;
