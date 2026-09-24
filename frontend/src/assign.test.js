import { describe, expect, it } from 'vitest';
import rankEngineers from './assign';

const engineer = (id, name, extra) => ({
  id, name, specialty: 'IT', on_shift_now: true, active_primary: 0, is_available: true, ...extra,
});

describe('rankEngineers', () => {
  it('puts the matching specialty, then on shift, then the lightest workload first', () => {
    const choices = rankEngineers([
      engineer(1, 'Busy IT', { active_primary: 4 }),
      engineer(2, 'Facilities', { specialty: 'facilities' }),
      engineer(3, 'Off-shift IT', { on_shift_now: false }),
      engineer(4, 'Free IT', { active_primary: 1 }),
    ], 'IT');
    expect(choices.map((choice) => choice.value)).toEqual(['4', '1', '3', '2']);
    expect(choices[0].label).toBe('Free IT · IT · on shift · 1 active (suggested)');
    expect(choices[1].label).not.toContain('suggested');
  });

  it('leaves out unavailable engineers and the current primary', () => {
    const choices = rankEngineers([
      engineer(1, 'Away', { is_available: false }),
      engineer(2, 'Current'),
      engineer(3, 'Other'),
    ], 'IT', 2);
    expect(choices.map((choice) => choice.value)).toEqual(['3']);
  });
});
