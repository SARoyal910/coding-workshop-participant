import { describe, expect, it } from 'vitest';
import { formatLocation, formatStatusAge } from './constants';

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

describe('formatLocation', () => {
  const base = { building_name: 'HQ', floor_number: 12 };

  it('shows the floor alone for shared areas', () => {
    expect(formatLocation(base)).toBe('HQ · Floor 12');
  });

  it('shows a single seat', () => {
    expect(formatLocation({ ...base, seat_code: '12-A-031' })).toBe('HQ · Floor 12 · Seat 12-A-031');
  });

  it('counts the extra seats in lists', () => {
    expect(formatLocation({ ...base, seat_code: '12-A-031', seat_count: 3 }))
      .toBe('HQ · Floor 12 · Seat 12-A-031 +2 more');
  });

  it('lists every seat when they are known', () => {
    const seats = [{ code: '12-A-031' }, { code: '12-A-032' }];
    expect(formatLocation({ ...base, seat_code: '12-A-031', seats }))
      .toBe('HQ · Floor 12 · Seats 12-A-031, 12-A-032');
  });
});
