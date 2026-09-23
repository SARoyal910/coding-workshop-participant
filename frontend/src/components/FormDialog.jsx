import { useState } from 'react';
import PropTypes from 'prop-types';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';

/**
 * Turn the form's text values into the request body: numbers for number
 * fields, and null for an empty optional field.
 * @param {Array<Object>} fields
 * @param {Object<string, string>} values
 * @returns {Object}
 */
function toBody(fields, values) {
  const body = {};
  fields.forEach((field) => {
    const value = String(values[field.name] ?? '').trim();
    if (field.type === 'number') body[field.name] = value === '' ? null : Number(value);
    else if (value === '' && !field.required) body[field.name] = null;
    else body[field.name] = value;
  });
  return body;
}

/**
 * A small create/edit form in a dialog, described by a list of fields.
 * Required fields are checked before sending; errors from the API (400
 * details) appear under the matching field, and any other error at the top.
 *
 * @param {{
 *   open: boolean, title: string, submitLabel?: string,
 *   fields: Array<{name: string, label: string, type?: string, required?: boolean,
 *     options?: Object<string, string>, maxLength?: number, helperText?: string}>,
 *   initialValues?: Object, onCancel: function, onSubmit: function(Object): Promise<*>
 * }} props
 * @returns {JSX.Element}
 */
export default function FormDialog({
  open, title, submitLabel = 'Save', fields, initialValues = {}, onCancel, onSubmit,
}) {
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Start from the initial values each time the dialog opens.
  const reset = () => {
    const start = {};
    fields.forEach((field) => { start[field.name] = initialValues[field.name] ?? ''; });
    setValues(start);
    setErrors({});
    setFormError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const missing = {};
    fields.forEach((field) => {
      if (field.required && !String(values[field.name] ?? '').trim()) missing[field.name] = 'This field is required';
    });
    setErrors(missing);
    if (Object.keys(missing).length) return;

    setSubmitting(true);
    setFormError('');
    try {
      await onSubmit(toBody(fields, values));
    } catch (err) {
      const fieldErrors = err.details || {};
      setErrors(fieldErrors);
      // Show the message at the top unless every problem is shown on a field.
      const onFields = Object.keys(fieldErrors).length
        && Object.keys(fieldErrors).every((name) => fields.some((field) => field.name === name));
      if (!onFields) setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={submitting ? undefined : onCancel}
      fullWidth
      maxWidth="sm"
      slotProps={{ transition: { onEnter: reset } }}
    >
      <form onSubmit={handleSubmit} noValidate>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {formError && <Alert severity="error">{formError}</Alert>}
            {fields.map((field, index) => (
              <TextField
                key={field.name}
                autoFocus={index === 0}
                select={Boolean(field.options)}
                type={field.type === 'number' || field.type === 'password' ? field.type : 'text'}
                label={field.label}
                value={values[field.name] ?? ''}
                onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
                required={field.required}
                error={Boolean(errors[field.name])}
                helperText={errors[field.name] || field.helperText}
                disabled={submitting}
                fullWidth
                slotProps={{ htmlInput: field.maxLength ? { maxLength: field.maxLength } : undefined }}
              >
                {field.options && Object.entries(field.options).map(([value, text]) => (
                  <MenuItem key={value} value={value}>{text}</MenuItem>
                ))}
              </TextField>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onCancel} disabled={submitting}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={submitting}>
            {submitting ? 'Saving…' : submitLabel}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

FormDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  title: PropTypes.string.isRequired,
  submitLabel: PropTypes.string,
  fields: PropTypes.arrayOf(PropTypes.shape({
    name: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
    type: PropTypes.oneOf(['text', 'number', 'password']),
    required: PropTypes.bool,
    options: PropTypes.objectOf(PropTypes.string),
    maxLength: PropTypes.number,
    helperText: PropTypes.string,
  })).isRequired,
  initialValues: PropTypes.objectOf(PropTypes.oneOfType([PropTypes.string, PropTypes.number])),
  onCancel: PropTypes.func.isRequired,
  onSubmit: PropTypes.func.isRequired,
};
