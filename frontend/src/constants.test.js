import { describe, expect, it } from 'vitest';
import { formatStatusAge } from './constants';

describe('formatStatusAge', () => {
  const now = new Date('2026-09-23T12:00:00Z');
  const ago = (minutes) => new Date(now - minutes * 60000).toISOString();

  it.each([
    [0, '0 min'],
    [59, '59 min'],
    [60, '1 hour'],
    [23 * 60, '23 hours'],
    [24 * 60, '1 day'],
    [3 * 24 * 60 + 5, '3 days'],
  ])('%i minutes ago is "%s"', (minutes, expected) => {
    expect(formatStatusAge(ago(minutes), now)).toBe(expected);
  });

  it('returns null without a timestamp', () => {
    expect(formatStatusAge(null, now)).toBeNull();
  });
});
