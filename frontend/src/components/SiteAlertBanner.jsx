import { useCallback } from 'react';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import useApiData from '../hooks/useApiData';
import { incidentsApi } from '../services/api';
import {
  REFRESH_MS, STATUS_LABELS, formatLocation, formatStatusAge,
} from '../constants';

/**
 * Site-wide alert: every active critical incident, shown to every role on
 * every page. Reloads on each navigation so it clears once the incident is
 * resolved. Renders nothing when there are none or the request fails.
 * @returns {JSX.Element|null}
 */
export default function SiteAlertBanner() {
  const { pathname } = useLocation();
  // pathname is a dependency on purpose: a new page means a fresh check.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(() => incidentsApi.alerts(), [pathname]);
  const { data } = useApiData(loader, { refreshMs: REFRESH_MS });
  const alerts = data?.items || [];
  if (!alerts.length) return null;

  return (
    <Alert severity="error" variant="filled" sx={{ mb: 2 }} role="alert">
      <AlertTitle sx={{ fontWeight: 700 }}>
        {alerts.length === 1 ? 'Critical incident on site' : `${alerts.length} critical incidents on site`}
      </AlertTitle>
      <Stack spacing={0.5}>
        {alerts.map((alert) => (
          <Link
            key={alert.id}
            component={RouterLink}
            to={`/incidents/${alert.id}`}
            color="inherit"
            underline="hover"
            variant="body2"
          >
            {`#${alert.id} ${alert.title} · ${formatLocation(alert)} · ${STATUS_LABELS[alert.status]} for ${formatStatusAge(alert.status_since)}`}
          </Link>
        ))}
      </Stack>
    </Alert>
  );
}
