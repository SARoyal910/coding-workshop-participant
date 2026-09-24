import {
  afterEach, beforeEach, describe, expect, it, vi,
} from 'vitest';
import { act, renderHook } from '@testing-library/react';
import useApiData from './useApiData';

describe('useApiData background refresh', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  /** Let pending promises (the loader) settle inside act(). */
  const flush = () => act(async () => { await Promise.resolve(); });

  it('reloads on the interval', async () => {
    const loader = vi.fn(async () => 'data');
    renderHook(() => useApiData(loader, { refreshMs: 1000 }));
    await flush();
    expect(loader).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(1000); });
    await flush();
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it('pauses while refreshMs is 0 (a form is open) and resumes after', async () => {
    const loader = vi.fn(async () => 'data');
    const { rerender } = renderHook(({ refreshMs }) => useApiData(loader, { refreshMs }), {
      initialProps: { refreshMs: 1000 },
    });
    await flush();
    rerender({ refreshMs: 0 });
    await act(async () => { vi.advanceTimersByTime(5000); });
    await flush();
    expect(loader).toHaveBeenCalledTimes(1);

    rerender({ refreshMs: 1000 });
    await act(async () => { vi.advanceTimersByTime(1000); });
    await flush();
    expect(loader).toHaveBeenCalledTimes(2);
  });
});
