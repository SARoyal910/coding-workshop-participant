import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import WorkLogPanel from './WorkLogPanel';

const LIMIT = 'You already have 9 hours logged on this day across your tickets; the limit is 12 a day, so at most 3 more';

function renderPanel(onAdd) {
  return render(
    <WorkLogPanel logs={[]} currentUserId={20} canLog readOnly={false} onAdd={onAdd} onEdit={vi.fn()} />,
  );
}

describe('WorkLogPanel', () => {
  it('states the daily limit before anyone hits it', () => {
    renderPanel(vi.fn());
    expect(screen.getByText('Up to 12 hours a day across all your tickets, in 15-minute steps.')).toBeInTheDocument();
  });

  it('shows the daily-limit error from the server in full', async () => {
    const onAdd = vi.fn().mockResolvedValue({ hours: LIMIT });
    renderPanel(onAdd);
    fireEvent.change(screen.getByLabelText('What did you do?'), { target: { value: 'Rewired the dock' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(LIMIT);
    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ description: 'Rewired the dock' }));
  });
});
