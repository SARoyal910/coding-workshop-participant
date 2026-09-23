import { Component } from 'react';
import PropTypes from 'prop-types';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

/**
 * Catches rendering errors below it and shows a friendly fallback with a
 * Reload button instead of a blank screen (DESIGN.md 13.8).
 * Error boundaries must be class components in React.
 */
export default class ErrorBoundary extends Component {
  /** @param {{children: React.ReactNode}} props */
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  /** Switch to the fallback UI after an error. */
  static getDerivedStateFromError() {
    return { hasError: true };
  }

  /** Log the error for debugging. */
  componentDidCatch(error, info) {
    console.error('Page crashed', error, info.componentStack);
  }

  /** @returns {JSX.Element} */
  render() {
    const { hasError } = this.state;
    const { children } = this.props;
    if (!hasError) return children;
    return (
      <Box role="alert" sx={{ textAlign: 'center', py: 8, px: 2 }}>
        <Typography variant="h5" gutterBottom>Something went wrong</Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          This page hit an unexpected error. Reloading usually fixes it.
        </Typography>
        <Button variant="contained" onClick={() => window.location.reload()}>Reload</Button>
      </Box>
    );
  }
}

ErrorBoundary.propTypes = {
  children: PropTypes.node.isRequired,
};
