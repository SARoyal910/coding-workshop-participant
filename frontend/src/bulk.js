/**
 * Bulk actions call the normal one-ticket endpoint for each selected item, so
 * every permission and version check still happens on the server. One item
 * failing (for example someone else changed that ticket) doesn't stop the rest.
 */

/**
 * Run `call` for every item at once and collect the failures.
 * @template T
 * @param {T[]} items
 * @param {function(T): Promise<*>} call
 * @returns {Promise<{done: number, failed: Array<{item: T, message: string}>}>}
 */
export async function runBulk(items, call) {
  const results = await Promise.allSettled(items.map((item) => call(item)));
  const failed = [];
  results.forEach((result, index) => {
    if (result.status === 'rejected') {
      failed.push({ item: items[index], message: result.reason?.message || 'Something went wrong' });
    }
  });
  return { done: items.length - failed.length, failed };
}

/**
 * Summarise a bulk run for a snackbar, e.g. "Voided 3 tickets" or
 * "Voided 2 tickets. 1 failed: #12 This ticket changed since you loaded it".
 * @param {string} verb Past tense, e.g. "Voided".
 * @param {{done: number, failed: Array<{item: *, message: string}>}} result
 * @param {function(*): string} name How to name a failed item, e.g. (item) => `#${item.id}`.
 * @returns {{text: string, severity: string}}
 */
export function bulkSummary(verb, { done, failed }, name) {
  const count = (n) => `${n} ${n === 1 ? 'ticket' : 'tickets'}`;
  if (!failed.length) return { text: `${verb} ${count(done)}`, severity: 'success' };
  const reasons = failed.map(({ item, message }) => `${name(item)} ${message}`).join('; ');
  const text = done ? `${verb} ${count(done)}. ${failed.length} failed: ${reasons}` : `Nothing changed. ${reasons}`;
  return { text, severity: done ? 'warning' : 'error' };
}
