import { useCallback, useState } from 'react';
import PropTypes from 'prop-types';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TablePagination from '@mui/material/TablePagination';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import ActionDialog from '../components/ActionDialog';
import FormDialog from '../components/FormDialog';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import useApiData from '../hooks/useApiData';
import useNotify from '../hooks/useNotify';
import { facilitiesApi } from '../services/api';

const PAGE_SIZE = 10;

/** Form fields for each kind of place (limits match the API). */
const FIELDS = {
  building: [
    { name: 'name', label: 'Name', required: true, maxLength: 100 },
    { name: 'address', label: 'Address', required: true, maxLength: 200 },
  ],
  floor: [
    { name: 'number', label: 'Floor number', type: 'number', required: true, helperText: 'Use 0 or below for ground and basement floors' },
  ],
  seat: [
    { name: 'code', label: 'Seat code', required: true, maxLength: 20, helperText: 'e.g. 12-A-034' },
  ],
};

const NAMES = { building: 'building', floor: 'floor', seat: 'seat' };
const TITLES = { building: 'Building', floor: 'Floor', seat: 'Seat' };

/**
 * "3 incidents" / "1 incident".
 * @param {number} count
 * @returns {string}
 */
function incidentText(count) {
  return `${count} incident${count === 1 ? '' : 's'}`;
}

/**
 * Edit and delete buttons for one place. Delete is disabled (with the reason
 * as a tooltip) when incidents point at it, because the API would refuse.
 * @param {{label: string, incidentCount: number, onEdit: function, onDelete: function}} props
 * @returns {JSX.Element}
 */
function PlaceActions({
  label, incidentCount, onEdit, onDelete,
}) {
  const locked = incidentCount > 0;
  return (
    <Stack direction="row">
      <Tooltip title={`Edit ${label}`}>
        <IconButton size="small" aria-label={`Edit ${label}`} onClick={onEdit}><EditOutlinedIcon fontSize="small" /></IconButton>
      </Tooltip>
      <Tooltip title={locked ? `Can't delete: ${incidentText(incidentCount)} reported here` : `Delete ${label}`}>
        {/* The span keeps the tooltip working on a disabled button. */}
        <span>
          <IconButton size="small" aria-label={`Delete ${label}`} onClick={onDelete} disabled={locked}>
            <DeleteOutlinedIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
    </Stack>
  );
}

PlaceActions.propTypes = {
  label: PropTypes.string.isRequired,
  incidentCount: PropTypes.number.isRequired,
  onEdit: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
};

const seatShape = PropTypes.shape({ id: PropTypes.number, code: PropTypes.string, incident_count: PropTypes.number });
const floorShape = PropTypes.shape({
  id: PropTypes.number, number: PropTypes.number, incident_count: PropTypes.number, seats: PropTypes.arrayOf(seatShape),
});
const buildingShape = PropTypes.shape({
  id: PropTypes.number, name: PropTypes.string, address: PropTypes.string, incident_count: PropTypes.number,
  floors: PropTypes.arrayOf(floorShape),
});

/**
 * One building: its details, then each floor with its seats.
 * @param {{building: Object, onForm: function, onDelete: function}} props
 *   onForm(kind, {item?, parentId?}) opens the add/edit form; onDelete(kind, item) asks to delete.
 * @returns {JSX.Element}
 */
function BuildingCard({ building, onForm, onDelete }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Typography variant="h6" component="h2">{building.name}</Typography>
            <PlaceActions
              label={building.name}
              incidentCount={building.incident_count}
              onEdit={() => onForm('building', { item: building })}
              onDelete={() => onDelete('building', building)}
            />
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {`${building.address} · ${incidentText(building.incident_count)}`}
          </Typography>
        </Box>
        <Button size="small" startIcon={<AddIcon />} onClick={() => onForm('floor', { parentId: building.id })}>
          Add floor
        </Button>
      </Stack>

      <Divider sx={{ my: 1.5 }} />
      {!building.floors.length && <Typography color="text.secondary">No floors yet.</Typography>}
      <Stack spacing={1.5} divider={<Divider flexItem />}>
        {building.floors.map((floor) => (
          <Box key={floor.id}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography sx={{ fontWeight: 600 }}>{`Floor ${floor.number}`}</Typography>
              <Typography variant="body2" color="text.secondary">{incidentText(floor.incident_count)}</Typography>
              <PlaceActions
                label={`floor ${floor.number}`}
                incidentCount={floor.incident_count}
                onEdit={() => onForm('floor', { item: floor })}
                onDelete={() => onDelete('floor', floor)}
              />
              <Box sx={{ flexGrow: 1 }} />
              <Button size="small" startIcon={<AddIcon />} onClick={() => onForm('seat', { parentId: floor.id })}>
                Add seat
              </Button>
            </Stack>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mt: 1 }}>
              {!floor.seats.length && <Typography variant="body2" color="text.secondary">No seats (incidents can still be reported for the whole floor).</Typography>}
              {floor.seats.map((seat) => (
                <Tooltip key={seat.id} describeChild title={`${incidentText(seat.incident_count)} · click to rename`}>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={seat.incident_count ? `${seat.code} (${seat.incident_count})` : seat.code}
                    onClick={() => onForm('seat', { item: seat })}
                    // Only seats without incidents get a delete (x) button.
                    onDelete={seat.incident_count ? undefined : () => onDelete('seat', seat)}
                  />
                </Tooltip>
              ))}
            </Box>
          </Box>
        ))}
      </Stack>
    </Paper>
  );
}

BuildingCard.propTypes = {
  building: buildingShape.isRequired,
  onForm: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
};

/**
 * Admin page for buildings, floors and seats. The number of incidents at
 * each place is shown, and places with incidents can't be deleted.
 * @returns {JSX.Element}
 */
export default function FacilitiesPage() {
  const { notify } = useNotify();
  const [page, setPage] = useState(1);
  const loader = useCallback(() => facilitiesApi.list({ page, page_size: PAGE_SIZE }), [page]);
  const {
    data, error, loading, reload,
  } = useApiData(loader);
  // Open form: {kind, item?, parentId?}. Pending delete: {kind, item}.
  const [form, setForm] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const openForm = (kind, target) => setForm({ kind, ...target });

  /** Create or update, depending on whether the form was opened for an existing item. */
  const handleSave = async (body) => {
    const { kind, item, parentId } = form;
    const calls = {
      building: [facilitiesApi.createBuilding, facilitiesApi.updateBuilding],
      floor: [facilitiesApi.createFloor, facilitiesApi.updateFloor],
      seat: [facilitiesApi.createSeat, facilitiesApi.updateSeat],
    };
    const [create, update] = calls[kind];
    if (item) await update(item.id, body);
    else if (kind === 'building') await create(body);
    else await create(parentId, body);
    setForm(null);
    notify(`${TITLES[kind]} ${item ? 'updated' : 'added'}`);
    reload();
  };

  const handleDelete = async () => {
    const { kind, item } = toDelete;
    const calls = { building: facilitiesApi.deleteBuilding, floor: facilitiesApi.deleteFloor, seat: facilitiesApi.deleteSeat };
    setDeleting(true);
    try {
      await calls[kind](item.id);
      notify(`Deleted ${NAMES[kind]}`);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setDeleting(false);
      setToDelete(null);
      reload();
    }
  };

  /** What the delete dialog says will go, including everything inside it. */
  const deleteDescription = () => {
    if (!toDelete) return '';
    const { kind, item } = toDelete;
    if (kind === 'building') {
      const seats = item.floors.reduce((sum, floor) => sum + floor.seats.length, 0);
      return `This also deletes its ${item.floors.length} floor(s) and ${seats} seat(s). This can't be undone.`;
    }
    if (kind === 'floor') return `This also deletes its ${item.seats.length} seat(s). This can't be undone.`;
    return "This can't be undone.";
  };

  const formTitle = () => {
    if (!form) return '';
    const name = NAMES[form.kind];
    return form.item ? `Edit ${name}` : `Add ${name}`;
  };

  let content;
  if (loading && !data) content = <LoadingState label="Loading facilities…" />;
  else if (error) content = <ErrorState error={error} onRetry={reload} />;
  else if (!data.items.length) {
    content = (
      <EmptyState
        title="No buildings yet"
        message="Add a building, then its floors and seats, so employees can report incidents there."
      />
    );
  } else {
    content = (
      <Stack spacing={2}>
        {data.items.map((building) => (
          <BuildingCard
            key={building.id}
            building={building}
            onForm={openForm}
            onDelete={(kind, item) => setToDelete({ kind, item })}
          />
        ))}
        {data.total > PAGE_SIZE && (
          <TablePagination
            component="div"
            count={data.total}
            page={page - 1}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(event, newPage) => setPage(newPage + 1)}
          />
        )}
      </Stack>
    );
  }

  return (
    <Box>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2, gap: 2 }}>
        <Typography variant="h4" component="h1">Facilities</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => openForm('building', {})}>
          Add building
        </Button>
      </Stack>
      {content}

      <FormDialog
        open={Boolean(form)}
        title={formTitle()}
        submitLabel={form?.item ? 'Save' : 'Add'}
        fields={form ? FIELDS[form.kind] : []}
        // Only the form's own fields (a building item also carries its floors).
        initialValues={form?.item ? Object.fromEntries(FIELDS[form.kind].map((field) => [field.name, form.item[field.name]])) : {}}
        onCancel={() => setForm(null)}
        onSubmit={handleSave}
      />
      <ActionDialog
        open={Boolean(toDelete)}
        title={toDelete ? `Delete ${NAMES[toDelete.kind]} ${toDelete.item.name || toDelete.item.code || toDelete.item.number}?` : ''}
        description={deleteDescription()}
        confirmLabel="Delete"
        danger
        submitting={deleting}
        onCancel={() => setToDelete(null)}
        onConfirm={handleDelete}
      />
    </Box>
  );
}
