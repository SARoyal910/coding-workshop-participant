import {
  beforeEach, describe, expect, it, vi,
} from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SiteAlertBanner from './SiteAlertBanner';
import { incidentsApi } from '../services/api';

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, incidentsApi: { ...actual.incidentsApi, alerts: vi.fn() } };
});

const ALERT = {
  id: 7, title: 'Badge readers down', status: 'in_progress', building_name: 'HQ',
  floor_number: 2, seat_code: null, status_since: new Date().toISOString(),
};

function renderBanner() {
  return render(<MemoryRouter><SiteAlertBanner /></MemoryRouter>);
}

describe('SiteAlertBanner', () => {
  beforeEach(() => incidentsApi.alerts.mockReset());

  it('renders nothing when there are no critical incidents', async () => {
    incidentsApi.alerts.mockResolvedValue({ items: [] });
    const { container } = renderBanner();
    await vi.waitFor(() => expect(incidentsApi.alerts).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('links each critical incident with its location and status', async () => {
    incidentsApi.alerts.mockResolvedValue({ items: [ALERT] });
    renderBanner();
    expect(await screen.findByText('Critical incident on site')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /#7 Badge readers down · HQ · Floor 2 · In progress for/ });
    expect(link).toHaveAttribute('href', '/incidents/7');
  });
});
