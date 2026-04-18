import { renderHook, act } from '@testing-library/react';
import { useRetry } from '../hooks/useRetry';

describe('useRetry', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('succeeds on first try', async () => {
    const fn = jest.fn().mockResolvedValue('ok');
    const { result } = renderHook(() => useRetry(fn));

    let value: string | undefined;
    await act(async () => {
      value = await result.current.execute();
    });

    expect(value).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.attempts).toBe(0);
  });

  it('retries on failure and eventually succeeds', async () => {
    const fn = jest
      .fn()
      .mockRejectedValueOnce(new Error('fail 1'))
      .mockRejectedValueOnce(new Error('fail 2'))
      .mockResolvedValue('ok');

    const onRetry = jest.fn();
    const onSuccess = jest.fn();
    const { result } = renderHook(() =>
      useRetry(fn, {
        config: { maxRetries: 3, baseDelayMs: 10, maxDelayMs: 50, retryableStatuses: [] },
        onRetry,
        onSuccess,
      }),
    );

    let value: string | undefined;
    await act(async () => {
      const promise = result.current.execute();
      // Advance timers for retries
      jest.advanceTimersByTime(100);
      value = await promise;
    });

    expect(value).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(3);
    expect(onRetry).toHaveBeenCalledTimes(2);
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('calls onFailure after exhausting retries', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('always fails'));
    const onFailure = jest.fn();

    const { result } = renderHook(() =>
      useRetry(fn, {
        config: { maxRetries: 2, baseDelayMs: 10, maxDelayMs: 50, retryableStatuses: [] },
        onFailure,
      }),
    );

    await act(async () => {
      const promise = result.current.execute();
      jest.advanceTimersByTime(200);
      await expect(promise).rejects.toThrow('always fails');
    });

    expect(fn).toHaveBeenCalledTimes(3); // 1 initial + 2 retries
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('reset clears state', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() =>
      useRetry(fn, {
        config: { maxRetries: 0, baseDelayMs: 10, maxDelayMs: 50, retryableStatuses: [] },
      }),
    );

    await act(async () => {
      await result.current.execute().catch(() => {});
    });

    expect(result.current.error).not.toBeNull();

    act(() => {
      result.current.reset();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.attempts).toBe(0);
    expect(result.current.loading).toBe(false);
  });
});
