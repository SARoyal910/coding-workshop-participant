import {
  beforeEach, describe, expect, it, vi,
} from 'vitest';
import { loadOrReload } from './lazyWithReload';

describe('loadOrReload', () => {
  beforeEach(() => sessionStorage.clear());

  it('returns the module when it loads', async () => {
    const reload = vi.fn();
    await expect(loadOrReload(() => Promise.resolve({ default: 'Page' }), reload)).resolves.toEqual({ default: 'Page' });
    expect(reload).not.toHaveBeenCalled();
  });

  it('reloads once when a page file is missing after a deploy', async () => {
    const reload = vi.fn();
    const pending = loadOrReload(() => Promise.reject(new Error('Failed to fetch module')), reload);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    // It never settles, so the old page never renders while reloading.
    const settled = await Promise.race([pending.then(() => true, () => true), new Promise((r) => { setTimeout(() => r(false), 20); })]);
    expect(settled).toBe(false);
  });

  it('shows the error instead of reloading again if it still fails after the reload', async () => {
    sessionStorage.setItem('reloadedForNewVersion', '1');
    const reload = vi.fn();
    await expect(loadOrReload(() => Promise.reject(new Error('broken')), reload)).rejects.toThrow('broken');
    expect(reload).not.toHaveBeenCalled();
  });

  it('clears the guard once a page loads, so a later deploy can reload again', async () => {
    sessionStorage.setItem('reloadedForNewVersion', '1');
    await loadOrReload(() => Promise.resolve({}), vi.fn());
    expect(sessionStorage.getItem('reloadedForNewVersion')).toBeNull();
  });
});
