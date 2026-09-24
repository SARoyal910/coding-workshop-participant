import { describe, expect, it } from 'vitest';
import { bulkSummary, runBulk } from './bulk';

const name = (item) => `#${item.id}`;

describe('runBulk', () => {
  it('runs every item and collects the failures without stopping', async () => {
    const seen = [];
    const result = await runBulk([{ id: 1 }, { id: 2 }, { id: 3 }], async (item) => {
      seen.push(item.id);
      if (item.id === 2) throw new Error('This ticket changed');
    });
    expect(seen).toEqual([1, 2, 3]);
    expect(result).toEqual({ done: 2, failed: [{ item: { id: 2 }, message: 'This ticket changed' }] });
  });
});

describe('bulkSummary', () => {
  it('reports success', () => {
    expect(bulkSummary('Voided', { done: 3, failed: [] }, name)).toEqual({ text: 'Voided 3 tickets', severity: 'success' });
    expect(bulkSummary('Voided', { done: 1, failed: [] }, name).text).toBe('Voided 1 ticket');
  });

  it('names what failed alongside what worked', () => {
    const failed = [{ item: { id: 12 }, message: 'Already archived' }];
    expect(bulkSummary('Voided', { done: 2, failed }, name))
      .toEqual({ text: 'Voided 2 tickets. 1 failed: #12 Already archived', severity: 'warning' });
  });

  it('is an error when nothing worked', () => {
    const failed = [{ item: { id: 12 }, message: 'Forbidden' }];
    expect(bulkSummary('Voided', { done: 0, failed }, name))
      .toEqual({ text: 'Nothing changed. #12 Forbidden', severity: 'error' });
  });
});
