import { Suspense } from 'react';
import { Link as RouterLink, Route, Routes } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import Layout from './components/Layout';
import { LoadingState } from './components/PageState';
import RequireAuth from './components/RequireAuth';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import lazyWithReload from './lazyWithReload';

// Pages behind login are loaded on demand, so the login screen doesn't download
// the charts library and every page at once. lazyWithReload recovers tabs that
// were open across a deploy.
const ApprovalsPage = lazyWithReload(() => import('./pages/ApprovalsPage'));
const DashboardPage = lazyWithReload(() => import('./pages/DashboardPage'));
const EngineersPage = lazyWithReload(() => import('./pages/EngineersPage'));
const FacilitiesPage = lazyWithReload(() => import('./pages/FacilitiesPage'));
const IncidentDetailPage = lazyWithReload(() => import('./pages/IncidentDetailPage'));
const IncidentFormPage = lazyWithReload(() => import('./pages/IncidentFormPage'));
const IncidentListPage = lazyWithReload(() => import('./pages/IncidentListPage'));
const PeoplePage = lazyWithReload(() => import('./pages/PeoplePage'));

/**
 * Wrap a lazily loaded page with a loading fallback.
 * @param {React.ComponentType} Page
 * @returns {JSX.Element}
 */
function lazyPage(Page) {
  return <Suspense fallback={<LoadingState />}><Page /></Suspense>;
}

/**
 * Shown for unknown URLs inside the app.
 * @returns {JSX.Element}
 */
function NotFoundPage() {
  return (
    <Box sx={{ textAlign: 'center', py: 8 }}>
      <Typography variant="h5" gutterBottom>Page not found</Typography>
      <Button component={RouterLink} to="/" variant="contained">Go to dashboard</Button>
    </Box>
  );
}

/**
 * Routes. Everything except login and register requires a logged-in user and
 * renders inside the Layout (top bar + navigation + error boundary).
 * @returns {JSX.Element}
 */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={lazyPage(DashboardPage)} />
        <Route path="incidents" element={lazyPage(IncidentListPage)} />
        <Route path="incidents/new" element={lazyPage(IncidentFormPage)} />
        <Route path="incidents/:id" element={lazyPage(IncidentDetailPage)} />
        <Route path="approvals" element={<RequireAuth roles={['admin']}>{lazyPage(ApprovalsPage)}</RequireAuth>} />
        <Route path="engineers" element={<RequireAuth roles={['admin', 'engineer']}>{lazyPage(EngineersPage)}</RequireAuth>} />
        <Route path="facilities" element={<RequireAuth roles={['admin']}>{lazyPage(FacilitiesPage)}</RequireAuth>} />
        <Route path="people" element={<RequireAuth roles={['admin']}>{lazyPage(PeoplePage)}</RequireAuth>} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
