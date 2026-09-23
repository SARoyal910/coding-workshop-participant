import { useState } from 'react';
import PropTypes from 'prop-types';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { EmptyState } from './PageState';

const DESCRIPTION_MAX = 2000;
// 0.25 to 12 hours in quarter-hour steps (same rule as backend/incidents/rules.py).
const HOUR_OPTIONS = Array.from({ length: 48 }, (unused, index) => (index + 1) * 0.25);

/** Today's date as YYYY-MM-DD in the browser's timezone. */
function today() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/**
 * Add or edit form for one work log.
 * @param {{initial?: Object, submitLabel: string, onSubmit: function(Object): Promise<boolean>, onCancel?: function}} props
 * @returns {JSX.Element}
 */
function WorkLogForm({
  initial, submitLabel, onSubmit, onCancel,
}) {
  const [values, setValues] = useState({
    work_date: initial?.work_date || today(),
    hours: initial ? Number(initial.hours) : 1,
    description: initial?.description || '',
  });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!values.description.trim()) {
      setErrors({ description: 'Describe the work' });
      return;
    }
    setSaving(true);
    const result = await onSubmit({ ...values, description: values.description.trim() });
    setSaving(false);
    if (result === true) {
      if (!initial) setValues({ work_date: today(), hours: 1, description: '' });
      setErrors({});
    } else if (result && typeof result === 'object') {
      setErrors(result);
    }
  };

  const set = (field) => (event) => {
    setValues((current) => ({ ...current, [field]: event.target.value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  };

  return (
    <Stack component="form" onSubmit={handleSubmit} noValidate spacing={1.5}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
        <TextField
          type="date"
          label="Date"
          value={values.work_date}
          onChange={set('work_date')}
          error={Boolean(errors.work_date)}
          helperText={errors.work_date}
          disabled={saving}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: today() } }}
        />
        <TextField
          select
          label="Hours"
          value={values.hours}
          onChange={set('hours')}
          error={Boolean(errors.hours)}
          helperText={errors.hours}
          disabled={saving}
          sx={{ minWidth: 120 }}
        >
          {HOUR_OPTIONS.map((hours) => <MenuItem key={hours} value={hours}>{hours}</MenuItem>)}
        </TextField>
        <TextField
          label="What did you do?"
          value={values.description}
          onChange={set('description')}
          error={Boolean(errors.description)}
          helperText={errors.description}
          disabled={saving}
          fullWidth
          slotProps={{ htmlInput: { maxLength: DESCRIPTION_MAX } }}
        />
      </Stack>
      <Stack direction="row" spacing={1}>
        <Button type="submit" variant="contained" size="small" disabled={saving}>{saving ? 'Saving…' : submitLabel}</Button>
        {onCancel && <Button size="small" onClick={onCancel} disabled={saving}>Cancel</Button>}
      </Stack>
    </Stack>
  );
}

WorkLogForm.propTypes = {
  initial: PropTypes.shape({
    work_date: PropTypes.string, hours: PropTypes.oneOfType([PropTypes.number, PropTypes.string]), description: PropTypes.string,
  }),
  submitLabel: PropTypes.string.isRequired,
  onSubmit: PropTypes.func.isRequired,
  onCancel: PropTypes.func,
};

/**
 * Time logged on the ticket, with an add form for engineers on it and an
 * inline editor for each engineer's own entries.
 * @param {{logs: Object[], currentUserId: number, canLog: boolean, readOnly: boolean, onAdd: function, onEdit: function}} props
 * @returns {JSX.Element}
 */
export default function WorkLogPanel({
  logs, currentUserId, canLog, readOnly, onAdd, onEdit,
}) {
  const [editingId, setEditingId] = useState(null);
  const total = logs.reduce((sum, log) => sum + Number(log.hours), 0);

  return (
    <Stack spacing={3}>
      {logs.length ? (
        <TableContainer>
          <Table size="small" aria-label="Work log">
            <TableHead>
              <TableRow>
                <TableCell>Date</TableCell>
                <TableCell>Engineer</TableCell>
                <TableCell>Hours</TableCell>
                <TableCell>Work done</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {logs.map((log) => (editingId === log.id ? (
                <TableRow key={log.id}>
                  <TableCell colSpan={5}>
                    <WorkLogForm
                      initial={log}
                      submitLabel="Save"
                      onCancel={() => setEditingId(null)}
                      onSubmit={async (values) => {
                        const result = await onEdit(log.id, values);
                        if (result === true) setEditingId(null);
                        return result;
                      }}
                    />
                  </TableCell>
                </TableRow>
              ) : (
                <TableRow key={log.id}>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{log.work_date}</TableCell>
                  <TableCell>{log.engineer_name}</TableCell>
                  <TableCell>{Number(log.hours)}</TableCell>
                  <TableCell>
                    {log.description}
                    {log.edited_at && <Typography variant="caption" color="text.secondary">{' (edited)'}</Typography>}
                  </TableCell>
                  <TableCell align="right">
                    {!readOnly && log.engineer_id === currentUserId && (
                      <Button size="small" onClick={() => setEditingId(log.id)}>Edit</Button>
                    )}
                  </TableCell>
                </TableRow>
              )))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <EmptyState title="No work logged yet" message="Engineers on the ticket log their time here." />
      )}
      {logs.length > 0 && <Typography variant="body2" color="text.secondary">{`Total: ${total} hours`}</Typography>}
      {canLog && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>Log work</Typography>
          <WorkLogForm submitLabel="Add" onSubmit={onAdd} />
        </Box>
      )}
    </Stack>
  );
}

WorkLogPanel.propTypes = {
  logs: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.number.isRequired,
    engineer_id: PropTypes.number.isRequired,
    engineer_name: PropTypes.string.isRequired,
    work_date: PropTypes.string.isRequired,
    hours: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
    description: PropTypes.string.isRequired,
    edited_at: PropTypes.string,
  })).isRequired,
  currentUserId: PropTypes.number.isRequired,
  canLog: PropTypes.bool.isRequired,
  readOnly: PropTypes.bool.isRequired,
  onAdd: PropTypes.func.isRequired,
  onEdit: PropTypes.func.isRequired,
};
