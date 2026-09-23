import { useState } from 'react';
import PropTypes from 'prop-types';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import { STATUS_LABELS, TRANSITION_LABELS } from '../constants';

const REASON_MAX = 1000;
const NOTE_MAX = 2000;

/** What each target status asks for (mirrors backend/incidents/rules.py). */
const TEXT_FIELD = {
  blocked: {
    name: 'reason', label: 'Why is it blocked?', max: REASON_MAX, required: true,
  },
  resolved: {
    name: 'resolution_note', label: 'How was it resolved?', max: NOTE_MAX, required: true,
  },
};

const DESCRIPTIONS = {
  in_progress: 'Move this ticket to In progress.',
  blocked: 'The reason is shown to the reporter and on the admin dashboard.',
  resolved: 'Your note is added to the ticket so the reporter knows what was done.',
  closed: 'Closing asks an admin to approve. Once approved, the ticket is archived.',
};

/**
 * Confirms a workflow transition and collects the reason or resolution note
 * when the transition requires one.
 * @param {{target: string|null, submitting: boolean, onCancel: function, onConfirm: function(Object): void}} props
 * @returns {JSX.Element}
 */
export default function TransitionDialog({
  target, submitting, onCancel, onConfirm,
}) {
  const [text, setText] = useState('');
  const [touched, setTouched] = useState(false);
  const config = target ? TEXT_FIELD[target] : null;
  const missing = Boolean(config?.required && !text.trim());

  const handleClose = () => {
    setText('');
    setTouched(false);
    onCancel();
  };

  const handleConfirm = (event) => {
    event.preventDefault();
    setTouched(true);
    if (missing) return;
    onConfirm(config ? { [config.name]: text.trim() } : {});
    setText('');
    setTouched(false);
  };

  return (
    <Dialog open={Boolean(target)} onClose={submitting ? undefined : handleClose} fullWidth maxWidth="sm">
      <form onSubmit={handleConfirm} noValidate>
        <DialogTitle>{target ? `${TRANSITION_LABELS[target]}: ${STATUS_LABELS[target]}` : ''}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: config ? 2 : 0 }}>{target ? DESCRIPTIONS[target] : ''}</DialogContentText>
          {config && (
            <TextField
              autoFocus
              fullWidth
              multiline
              minRows={3}
              required
              label={config.label}
              value={text}
              onChange={(event) => setText(event.target.value)}
              error={touched && missing}
              helperText={touched && missing ? 'This is required' : `${text.length}/${config.max}`}
              disabled={submitting}
              slotProps={{ htmlInput: { maxLength: config.max } }}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} disabled={submitting}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={submitting}>
            {submitting ? 'Saving…' : 'Confirm'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

TransitionDialog.propTypes = {
  target: PropTypes.oneOf(['in_progress', 'blocked', 'resolved', 'closed']),
  submitting: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
};
