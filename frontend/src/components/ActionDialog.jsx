import { useState } from 'react';
import PropTypes from 'prop-types';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';

const TEXT_MAX = 1000;

/**
 * Confirmation dialog for a ticket action, with an optional choice (select)
 * and an optional text field (reason or note). Used for priority changes,
 * reopen requests, rejecting requests and voiding.
 *
 * @param {{
 *   open: boolean, title: string, description?: string, confirmLabel?: string, danger?: boolean,
 *   choiceLabel?: string, choices?: Array<{value: string, label: string}>, initialChoice?: string,
 *   textLabel?: string, textRequired?: boolean, submitting: boolean,
 *   onCancel: function, onConfirm: function({choice?: string, text?: string}): void
 * }} props
 * @returns {JSX.Element}
 */
export default function ActionDialog({
  open, title, description, confirmLabel = 'Confirm', danger = false,
  choiceLabel, choices, initialChoice = '', textLabel, textRequired = false,
  submitting, onCancel, onConfirm,
}) {
  const [choice, setChoice] = useState(initialChoice);
  const [text, setText] = useState('');
  const [touched, setTouched] = useState(false);
  const textMissing = Boolean(textLabel && textRequired && !text.trim());

  const reset = () => {
    setChoice(initialChoice);
    setText('');
    setTouched(false);
  };

  const handleCancel = () => {
    reset();
    onCancel();
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setTouched(true);
    if (textMissing || (choices && !choice)) return;
    onConfirm({ choice, text: text.trim() });
    reset();
  };

  return (
    <Dialog
      open={open}
      onClose={submitting ? undefined : handleCancel}
      fullWidth
      maxWidth="sm"
      // Start fresh each time it opens (e.g. show the current priority).
      slotProps={{ transition: { onEnter: reset } }}
    >
      <form onSubmit={handleSubmit} noValidate>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {description && <DialogContentText>{description}</DialogContentText>}
            {choices && (
              <TextField
                select
                label={choiceLabel}
                value={choice}
                onChange={(event) => setChoice(event.target.value)}
                disabled={submitting}
                fullWidth
              >
                {choices.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
              </TextField>
            )}
            {textLabel && (
              <TextField
                autoFocus={!choices}
                label={textLabel}
                value={text}
                onChange={(event) => setText(event.target.value)}
                required={textRequired}
                error={touched && textMissing}
                helperText={touched && textMissing ? 'This is required' : `${text.length}/${TEXT_MAX}`}
                disabled={submitting}
                multiline
                minRows={3}
                fullWidth
                slotProps={{ htmlInput: { maxLength: TEXT_MAX } }}
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancel} disabled={submitting}>Cancel</Button>
          <Button type="submit" variant="contained" color={danger ? 'error' : 'primary'} disabled={submitting}>
            {submitting ? 'Saving…' : confirmLabel}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

ActionDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  title: PropTypes.string.isRequired,
  description: PropTypes.string,
  confirmLabel: PropTypes.string,
  danger: PropTypes.bool,
  choiceLabel: PropTypes.string,
  choices: PropTypes.arrayOf(PropTypes.shape({ value: PropTypes.string, label: PropTypes.string })),
  initialChoice: PropTypes.string,
  textLabel: PropTypes.string,
  textRequired: PropTypes.bool,
  submitting: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
};
