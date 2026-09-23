import { useCallback, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import { NotifyContext } from './contexts';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Snackbar from '@mui/material/Snackbar';


/**
 * App-wide success/error messages shown in a Snackbar.
 * @param {{children: React.ReactNode}} props
 * @returns {JSX.Element}
 */
export function NotifyProvider({ children }) {
  const [message, setMessage] = useState(null);

  const notify = useCallback((text, severity = 'success', action = null) => {
    setMessage({
      text, severity, action, key: Date.now(),
    });
  }, []);

  const close = (event, reason) => {
    if (reason !== 'clickaway') setMessage(null);
  };

  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <NotifyContext.Provider value={value}>
      {children}
      <Snackbar
        key={message?.key}
        open={Boolean(message)}
        autoHideDuration={message?.action ? null : 5000}
        onClose={close}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {message ? (
          <Alert
            onClose={close}
            severity={message.severity}
            variant="filled"
            sx={{ width: '100%' }}
            action={message.action ? (
              <Button
                color="inherit"
                size="small"
                onClick={() => { message.action.onClick(); setMessage(null); }}
              >
                {message.action.label}
              </Button>
            ) : undefined}
          >
            {message.text}
          </Alert>
        ) : undefined}
      </Snackbar>
    </NotifyContext.Provider>
  );
}

NotifyProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

