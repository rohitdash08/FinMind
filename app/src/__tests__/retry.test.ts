import { computeDelay, defaultShouldRetry, withRetry, sleep } from '../lib/retry';

// ── computeDelay ──────────────────────────────────────────────────────────────

describe('computeDelay', () => {
  const cfg = {
    maxAttempts: 3,
    baseDelayMs: 500,
    maxDelayMs: 10_000,
    jitterFactor: 0, // deterministic for testing
  };

  it('doubles the base delay per attempt', () => {
    expect(computeDelay(0, cfg)).toBe(500);
    expect(computeDelay(1, cfg)).toBe(1_000);
    expect(computeDelay(2, cfg)).toBe(2_000);
    expect(computeDelay(3, cfg)).toBe(4_000);
  });

  it('caps at maxDelayMs', () => {
    expect(computeDelay(10, cfg)).toBeLessThanOrEqual(10_000);
  });

  it('returns >= 0 even with negative jitter', () => {
    const jittery = { ...cfg, jitterFactor: 1 };
    for (let i = 0; i < 20; i++) {
      expect(computeDelay(1, jittery)).toBeGreaterThanOrEqual(0);
    }
  });
});

// ── defaultShouldRetry ────────────────────────────────────────────────────────

describe('defaultShouldRetry', () => {
  it('retries on TypeError (network failure)', () => {
    expect(defaultShouldRetry(new TypeError('Failed to fetch'), 0)).toBe(true);
  });

  it('retries on 500', () => {
    expect(defaultShouldRetry(new Error('HTTP 500'), 0)).toBe(true);
  });

  it('retries on 429', () => {
    expect(defaultShouldRetry(new Error('HTTP 429'), 0)).toBe(true);
  });

  it('does NOT retry on 400', () => {
    expect(defaultShouldRetry(new Error('HTTP 400'), 0)).toBe(false);
  });

  it('does NOT retry on 404', () => {
    expect(defaultShouldRetry(new Error('HTTP 404'), 0)).toBe(false);
  });

  it('does NOT retry generic errors', () => {
    expect(defaultShouldRetry(new Error('something else'), 0)).toBe(false);
  });
});

// ── withRetry ─────────────────────────────────────────────────────────────────

describe('withRetry', () => {
  beforeEach(() => {
    jest.spyOn(global, 'setTimeout').mockImplementation((fn: TimerHandler) => {
      if (typeof fn === 'function') fn();
      return 0 as unknown as NodeJS.Timeout;
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('returns immediately on success', async () => {
    const fn = jest.fn().mockResolvedValue('ok');
    const result = await withRetry(fn, { maxAttempts: 3, baseDelayMs: 0, maxDelayMs: 0, jitterFactor: 0 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('retries on retryable errors and eventually succeeds', async () => {
    const fn = jest
      .fn()
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValue('recovered');

    const result = await withRetry(fn, { maxAttempts: 3, baseDelayMs: 0, maxDelayMs: 0, jitterFactor: 0 });
    expect(result).toBe('recovered');
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('throws after maxAttempts exhausted', async () => {
    const fn = jest.fn().mockRejectedValue(new TypeError('always fail'));
    await expect(
      withRetry(fn, { maxAttempts: 2, baseDelayMs: 0, maxDelayMs: 0, jitterFactor: 0 }),
    ).rejects.toThrow('always fail');
    // initial + 2 retries = 3
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it('does NOT retry on non-retryable errors', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('HTTP 400'));
    await expect(
      withRetry(fn, { maxAttempts: 3, baseDelayMs: 0, maxDelayMs: 0, jitterFactor: 0 }),
    ).rejects.toThrow('HTTP 400');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('calls onRetry callback', async () => {
    const onRetry = jest.fn();
    const fn = jest
      .fn()
      .mockRejectedValueOnce(new TypeError('net'))
      .mockResolvedValue('ok');

    await withRetry(fn, { maxAttempts: 3, baseDelayMs: 0, maxDelayMs: 0, jitterFactor: 0, onRetry });
    expect(onRetry).toHaveBeenCalledWith(1, 0, expect.any(TypeError));
  });
});
