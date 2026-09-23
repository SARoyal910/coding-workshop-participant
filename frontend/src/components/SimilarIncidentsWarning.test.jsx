import {
  beforeEach, describe, expect, it, vi,
} from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RecurringBadge from './RecurringBadge';
import SimilarIncidentsWarning from './SimilarIncidentsWarning';
import { incidentsApi } from '../services/api';

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, incidentsApi: { ...actual.incidentsApi, similar: vi.fn() } };
});

/**
 * Render the warning inside a router (it renders links).
 * @param {Object} props
 */
function renderWarning(props) {
  return render(<MemoryRouter><SimilarIncidentsWarning {...props} /></MemoryRouter>);
}

describe('RecurringBadge', () => {
  it('renders nothing without a level', () => {
    const { container } = render(<RecurringBadge level={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names the place with text, not only color', () => {
    render(<RecurringBadge level="floor" />);
    expect(screen.getByText('Recurring on this floor')).toBeInTheDocument();
  });
});

describe('SimilarIncidentsWarning', () => {
  beforeEach(() => incidentsApi.similar.mockReset());

  it('does not call the API until an issue type and floor are chosen', () => {
    const { container } = renderWarning({ issueType: 'Wi-Fi', floorId: '' });
    expect(incidentsApi.similar).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows open duplicates with links to the ones the user may open, and the recurring pattern', async () => {
    incidentsApi.similar.mockResolvedValue({
      open_count: 2,
      items: [{ id: 5, title: 'Wi-Fi keeps dropping', status: 'open' }],
      recurring: { level: 'seat', count: 5, window_days: 30 },
    });
    renderWarning({ issueType: 'Wi-Fi', floorId: 7, seatId: 40 });

    expect(await screen.findByText('Wi-Fi is already reported at this seat')).toBeInTheDocument();
    expect(incidentsApi.similar).toHaveBeenCalledWith({ issue_type: 'Wi-Fi', floor_id: 7, seat_id: 40 });
    expect(screen.getByRole('link', { name: '#5 Wi-Fi keeps dropping' })).toHaveAttribute('href', '/incidents/5');
    expect(screen.getByText(/and 1 more/)).toBeInTheDocument();
    expect(screen.getByText(/5 Wi-Fi incidents at this seat in the last 30 days/)).toBeInTheDocument();
  });

  it('stays quiet when nothing similar exists', async () => {
    incidentsApi.similar.mockResolvedValue({ open_count: 0, items: [], recurring: null });
    renderWarning({ issueType: 'Camera', floorId: 7 });
    await vi.waitFor(() => expect(incidentsApi.similar).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
