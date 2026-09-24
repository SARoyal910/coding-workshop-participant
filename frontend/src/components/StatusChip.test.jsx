import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusChip from './StatusChip';

describe('StatusChip', () => {
  it.each([
    ['open', 'Open'],
    ['in_progress', 'In progress'],
    ['blocked', 'Blocked'],
    ['resolved', 'Resolved'],
    ['closed', 'Closed'],
  ])('shows a readable label for %s', (status, label) => {
    render(<StatusChip status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('shows "Archived" instead of the status for archived tickets', () => {
    render(<StatusChip status="closed" archived />);
    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.queryByText('Closed')).not.toBeInTheDocument();
  });

  it('shows "Voided" for a voided ticket, even though it is also archived', () => {
    render(<StatusChip status="open" archived voided />);
    expect(screen.getByText('Voided')).toBeInTheDocument();
    expect(screen.queryByText('Archived')).not.toBeInTheDocument();
  });

  it('falls back to the raw value for an unknown status', () => {
    render(<StatusChip status="mystery" />);
    expect(screen.getByText('mystery')).toBeInTheDocument();
  });
});
