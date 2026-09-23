import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FormDialog from './FormDialog';
import { ApiError } from '../services/api';

const FIELDS = [
  { name: 'name', label: 'Name', required: true },
  { name: 'address', label: 'Address', required: true },
  { name: 'phone', label: 'Phone' },
];

/**
 * Render an open dialog with the given submit handler.
 * @param {function} onSubmit
 */
function renderDialog(onSubmit) {
  render(<FormDialog open title="Add building" fields={FIELDS} onCancel={() => {}} onSubmit={onSubmit} />);
}

describe('FormDialog', () => {
  it('checks required fields before calling the API', async () => {
    const onSubmit = vi.fn();
    renderDialog(onSubmit);
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getAllByText('This field is required')).toHaveLength(2);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('sends trimmed values and null for an empty optional field', async () => {
    const onSubmit = vi.fn().mockResolvedValue({});
    renderDialog(onSubmit);
    await userEvent.type(screen.getByLabelText(/Name/), '  Annex  ');
    await userEvent.type(screen.getByLabelText(/Address/), '9 River Rd');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSubmit).toHaveBeenCalledWith({ name: 'Annex', address: '9 River Rd', phone: null });
  });

  it('shows 400/409 field details from the API under the matching field', async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiError(409, 'A building with this name already exists', { name: 'This name is already used' }),
    );
    renderDialog(onSubmit);
    await userEvent.type(screen.getByLabelText(/Name/), 'HQ Tower');
    await userEvent.type(screen.getByLabelText(/Address/), 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('This name is already used')).toBeInTheDocument();
    // Every problem is on a field, so there is no extra banner.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows other errors at the top of the form', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new ApiError(0, "Can't reach the server."));
    renderDialog(onSubmit);
    await userEvent.type(screen.getByLabelText(/Name/), 'Annex');
    await userEvent.type(screen.getByLabelText(/Address/), 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the server.");
  });
});
