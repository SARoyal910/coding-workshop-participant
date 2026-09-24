import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { ErrorState, LoadingState } from '../components/PageState';
import SimilarIncidentsWarning from '../components/SimilarIncidentsWarning';
import useNotify from '../hooks/useNotify';
import useApiData from '../hooks/useApiData';
import { incidentsApi } from '../services/api';
import { CATEGORY_LABELS, PRIORITY_LABELS } from '../constants';

const TITLE_MAX = 200;
const DESCRIPTION_MAX = 5000;
const SEATS_MAX = 20;

const EMPTY_FORM = {
  title: '',
  description: '',
  category: '',
  issue_type: '',
  priority: 'medium',
  building_id: '',
  floor_id: '',
  seat_ids: [],
};

/** Loads the form options once; defined outside the component so it never changes. */
const loadOptions = () => incidentsApi.options();

/**
 * Check required fields before sending, using the same limits as the API.
 * @param {typeof EMPTY_FORM} values
 * @returns {Object<string, string>} Field name -> message.
 */
function validate(values) {
  const errors = {};
  if (!values.title.trim()) errors.title = 'Give the incident a short title';
  if (!values.description.trim()) errors.description = 'Describe what is wrong';
  if (!values.category) errors.category = 'Choose a category';
  if (!values.issue_type) errors.issue_type = 'Choose an issue type';
  if (!values.building_id) errors.building_id = 'Choose a building';
  if (!values.floor_id) errors.floor_id = 'Choose a floor';
  return errors;
}

/**
 * Report a new incident. Choosing a category limits the issue types, and
 * choosing a building then floor limits the seats, so the location is always
 * consistent. Server-side validation errors appear on the matching field.
 * @returns {JSX.Element}
 */
export default function IncidentFormPage() {
  const navigate = useNavigate();
  const { notify } = useNotify();
  const {
    data: options, error: loadError, loading, reload,
  } = useApiData(loadOptions);
  const [values, setValues] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (loading) return <LoadingState label="Loading form…" />;
  if (loadError) return <ErrorState error={loadError} onRetry={reload} />;

  const building = options.buildings.find((item) => String(item.id) === String(values.building_id));
  const floor = building?.floors.find((item) => String(item.id) === String(values.floor_id));

  /** Update a field and clear the fields that depend on it. */
  const setField = (field, value) => {
    const next = { ...values, [field]: value };
    if (field === 'category') next.issue_type = '';
    if (field === 'building_id') { next.floor_id = ''; next.seat_ids = []; }
    if (field === 'floor_id') next.seat_ids = [];
    setValues(next);
    setErrors((current) => ({ ...current, [field]: undefined }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitError('');
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length) return;

    setSubmitting(true);
    try {
      const created = await incidentsApi.create({
        title: values.title.trim(),
        description: values.description.trim(),
        category: values.category,
        issue_type: values.issue_type,
        priority: values.priority,
        building_id: Number(values.building_id),
        floor_id: Number(values.floor_id),
        // One seat is sent as seat_id; a row of desks as seat_ids.
        ...(values.seat_ids.length === 1 ? { seat_id: values.seat_ids[0] } : {}),
        ...(values.seat_ids.length > 1 ? { seat_ids: values.seat_ids } : {}),
      });
      notify(`Incident #${created.id} reported`);
      navigate(`/incidents/${created.id}`);
    } catch (err) {
      setErrors(err.details || {});
      setSubmitError(err.message);
      setSubmitting(false);
    }
  };

  /** Common props for each field: value, change handler, error text. */
  const field = (name) => ({
    value: values[name],
    onChange: (event) => setField(name, event.target.value),
    error: Boolean(errors[name]),
    helperText: errors[name],
    disabled: submitting,
    fullWidth: true,
  });

  return (
    <Box sx={{ maxWidth: 820 }}>
      <Typography variant="h4" component="h1" gutterBottom>Report an incident</Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Tell us what is wrong and where. An engineer will pick it up from here.
      </Typography>

      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack component="form" spacing={3} onSubmit={handleSubmit} noValidate>
          {submitError && <Alert severity="error" role="alert">{submitError}</Alert>}

          <TextField
            label="Title"
            required
            {...field('title')}
            helperText={errors.title || `${values.title.length}/${TITLE_MAX}`}
            slotProps={{ htmlInput: { maxLength: TITLE_MAX } }}
          />
          <TextField
            label="Description"
            required
            multiline
            minRows={4}
            {...field('description')}
            helperText={errors.description || 'What happened, since when, and who is affected?'}
            slotProps={{ htmlInput: { maxLength: DESCRIPTION_MAX } }}
          />

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField select label="Category" required {...field('category')}>
                {Object.keys(options.issue_types).map((category) => (
                  <MenuItem key={category} value={category}>{CATEGORY_LABELS[category] || category}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                select
                label="Issue type"
                required
                {...field('issue_type')}
                disabled={submitting || !values.category}
                helperText={errors.issue_type || (!values.category ? 'Choose a category first' : '')}
              >
                {(options.issue_types[values.category] || []).map((type) => (
                  <MenuItem key={type} value={type}>{type}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField select label="Priority" {...field('priority')}>
                {options.priorities.map((priority) => (
                  <MenuItem key={priority} value={priority}>{PRIORITY_LABELS[priority]}</MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Building" required {...field('building_id')}>
                {options.buildings.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label="Floor" required {...field('floor_id')} disabled={submitting || !building}>
                {(building?.floors || []).map((item) => (
                  <MenuItem key={item.id} value={item.id}>{`Floor ${item.number}`}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Autocomplete
                multiple
                disableCloseOnSelect
                options={floor?.seats || []}
                getOptionLabel={(item) => item.code}
                value={(floor?.seats || []).filter((item) => values.seat_ids.includes(item.id))}
                onChange={(event, chosen) => setField('seat_ids', chosen.slice(0, SEATS_MAX).map((item) => item.id))}
                disabled={submitting || !floor}
                limitTags={6}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Seats (optional)"
                    error={Boolean(errors.seat_ids || errors.seat_id)}
                    helperText={errors.seat_ids || errors.seat_id || 'Pick one or more, or leave empty for shared areas'}
                  />
                )}
              />
            </Grid>
          </Grid>

          <SimilarIncidentsWarning issueType={values.issue_type} floorId={values.floor_id} seatId={values.seat_ids[0] || ''} />

          <Stack direction="row" spacing={1.5} sx={{ justifyContent: 'flex-end' }}>
            <Button onClick={() => navigate(-1)} disabled={submitting}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={submitting}>
              {submitting ? 'Submitting…' : 'Submit incident'}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  );
}
