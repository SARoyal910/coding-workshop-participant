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
    // A tighter scale than MUI's default: page titles stay prominent without
    // dwarfing the dense tables and forms below them.
    h4: { fontSize: '1.75rem', fontWeight: 700, lineHeight: 1.25, letterSpacing: '-0.01em' },
    h5: { fontSize: '1.375rem', fontWeight: 700, lineHeight: 1.3, letterSpacing: '-0.005em' },
    h6: { fontSize: '1.0625rem', fontWeight: 600, lineHeight: 1.4 },
    body1: { lineHeight: 1.55 },
    body2: { lineHeight: 1.5 },
    caption: { lineHeight: 1.4 },
    overline: { fontWeight: 600, letterSpacing: '0.08em', lineHeight: 1.6 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    // Column headings read as labels, distinct from the data under them.
    MuiTableCell: {
      styleOverrides: {
        head: ({ theme: t }) => ({
          fontSize: '0.8125rem', fontWeight: 600, color: t.palette.text.secondary, whiteSpace: 'nowrap',
        }),
      },
    },
    MuiChip: { styleOverrides: { label: { fontWeight: 500 } } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
    MuiPaper: { defaultProps: { variant: 'outlined' } },
    MuiAppBar: { defaultProps: { elevation: 0 } },
  },
});

export default theme;
