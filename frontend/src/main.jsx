import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import { AuthProvider } from './context/AuthContext';
import { NotifyProvider } from './context/NotifyContext';
import theme from './theme';
import './index.css';

// HashRouter keeps routes after the '#', so a refresh or shared link always
// requests '/' from CloudFront. The S3 origin answers 403 (not 404) for paths
// that aren't files, and CloudFront only rewrites 404s to index.html.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ErrorBoundary>
        <HashRouter>
          <NotifyProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </NotifyProvider>
        </HashRouter>
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>,
);
