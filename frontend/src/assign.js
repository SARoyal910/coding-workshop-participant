import { CATEGORY_LABELS } from './constants';

/**
 * Order engineers for the admin's Assign dialog, best candidate first:
 * available only, then the ticket's specialty, then on shift now, then the
 * fewest active tickets as primary. The current primary is left out.
 * @param {Object[]} engineers From GET /api/engineers.
 * @param {string} category The ticket's category (same values as specialties).
 * @param {number|null} currentPrimaryId
 * @returns {Array<{value: string, label: string}>} Choices for ActionDialog; the first is marked suggested.
 */
export default function rankEngineers(engineers, category, currentPrimaryId = null) {
  const score = (engineer) => [
    engineer.specialty === category ? 0 : 1,
    engineer.on_shift_now ? 0 : 1,
    engineer.active_primary,
  ];
  const compare = (a, b) => {
    const [x, y] = [score(a), score(b)];
    for (let i = 0; i < x.length; i += 1) if (x[i] !== y[i]) return x[i] - y[i];
    return a.name.localeCompare(b.name);
  };
  return engineers
    .filter((engineer) => engineer.is_available && engineer.id !== currentPrimaryId)
    .sort(compare)
    .map((engineer, index) => {
      const parts = [
        engineer.name,
        CATEGORY_LABELS[engineer.specialty] || engineer.specialty,
        engineer.on_shift_now ? 'on shift' : 'off shift',
        `${engineer.active_primary} active`,
      ];
      return { value: String(engineer.id), label: `${parts.join(' · ')}${index === 0 ? ' (suggested)' : ''}` };
    });
}
