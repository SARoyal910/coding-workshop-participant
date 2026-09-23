import { useState } from 'react';
import PropTypes from 'prop-types';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { EmptyState } from './PageState';
import { ROLE_LABELS, formatDateTime } from '../constants';

const NOTE_MAX = 2000;

const noteShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  body: PropTypes.string.isRequired,
  author_id: PropTypes.number.isRequired,
  author_name: PropTypes.string.isRequired,
  author_role: PropTypes.string.isRequired,
  created_at: PropTypes.string.isRequired,
  edited_at: PropTypes.string,
});

/**
 * One note, with an inline editor when the current user wrote it.
 * @param {{note: Object, canEdit: boolean, onSave: function(number, string): Promise<boolean>}} props
 * @returns {JSX.Element}
 */
function NoteItem({ note, canEdit, onSave }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(note.body);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    const ok = await onSave(note.id, text.trim());
    setSaving(false);
    if (ok) setEditing(false);
  };

  return (
    <Stack direction="row" spacing={1.5} component="li" sx={{ listStyle: 'none' }}>
      <Avatar sx={{ width: 36, height: 36, fontSize: 14 }} aria-hidden>
        {note.author_name.split(' ').map((part) => part[0]).join('').slice(0, 2)}
      </Avatar>
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{note.author_name}</Typography>
          <Chip label={ROLE_LABELS[note.author_role] || note.author_role} size="small" variant="outlined" />
          <Typography variant="caption" color="text.secondary">
            {formatDateTime(note.created_at)}
            {note.edited_at ? ' (edited)' : ''}
          </Typography>
        </Stack>
        {editing ? (
          <Stack spacing={1} sx={{ mt: 1 }}>
            <TextField
              multiline
              minRows={2}
              fullWidth
              value={text}
              onChange={(event) => setText(event.target.value)}
              disabled={saving}
              label="Edit note"
              slotProps={{ htmlInput: { maxLength: NOTE_MAX } }}
            />
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="contained" onClick={save} disabled={saving || !text.trim()}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
              <Button size="small" onClick={() => { setEditing(false); setText(note.body); }} disabled={saving}>
                Cancel
              </Button>
            </Stack>
          </Stack>
        ) : (
          <>
            <Typography sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>{note.body}</Typography>
            {canEdit && <Button size="small" onClick={() => setEditing(true)} sx={{ mt: 0.5, px: 0 }}>Edit</Button>}
          </>
        )}
      </Box>
    </Stack>
  );
}

NoteItem.propTypes = {
  note: noteShape.isRequired,
  canEdit: PropTypes.bool.isRequired,
  onSave: PropTypes.func.isRequired,
};

/**
 * The ticket's notes (append-only) and a box to add a new one.
 * @param {{notes: Object[], currentUserId: number, canAdd: boolean, onAdd: function, onEdit: function}} props
 * @returns {JSX.Element}
 */
export default function NotesPanel({
  notes, currentUserId, canAdd, onAdd, onEdit,
}) {
  const [text, setText] = useState('');
  const [adding, setAdding] = useState(false);

  const handleAdd = async (event) => {
    event.preventDefault();
    setAdding(true);
    const ok = await onAdd(text.trim());
    setAdding(false);
    if (ok) setText('');
  };

  return (
    <Stack spacing={3}>
      {notes.length ? (
        <Stack component="ul" spacing={2.5} sx={{ p: 0, m: 0 }}>
          {notes.map((note) => (
            <NoteItem
              key={note.id}
              note={note}
              canEdit={canAdd && note.author_id === currentUserId}
              onSave={onEdit}
            />
          ))}
        </Stack>
      ) : (
        <EmptyState title="No notes yet" message="Notes keep the reporter and engineers in the loop." />
      )}

      {canAdd && (
        <Stack component="form" spacing={1} onSubmit={handleAdd}>
          <TextField
            label="Add a note"
            multiline
            minRows={2}
            fullWidth
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={adding}
            helperText={`${text.length}/${NOTE_MAX}`}
            slotProps={{ htmlInput: { maxLength: NOTE_MAX } }}
          />
          <Box>
            <Button type="submit" variant="contained" disabled={adding || !text.trim()}>
              {adding ? 'Adding…' : 'Add note'}
            </Button>
          </Box>
        </Stack>
      )}
    </Stack>
  );
}

NotesPanel.propTypes = {
  notes: PropTypes.arrayOf(noteShape).isRequired,
  currentUserId: PropTypes.number.isRequired,
  canAdd: PropTypes.bool.isRequired,
  onAdd: PropTypes.func.isRequired,
  onEdit: PropTypes.func.isRequired,
};
