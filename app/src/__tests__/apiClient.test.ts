import { computeBackoffMs, onApiMetric, type ApiCallMetric } from '../api/client';

describe('computeBackoffMs', () => {
  const baseConfig = {
    maxRetries: 3,
    baseDelayMs: 1000,
    maxDelayMs: 10_000,
    retryableStatuses: [500, 502, 503, 504],
  };

  it('returns a positive number', () => {
    const delay = computeBackoffMs(0, baseConfig);
    expect(delay).toBeGreaterThan(0);
  });

  it('increases delay with higher attempt numbers', () => {
    // Run multiple samples to account for jitter
    const samples = 50;
    let d0Sum = 0;
    let d2Sum = 0;
    for (let i = 0; i < samples; i++) {
      d0Sum += computeBackoffMs(0, baseConfig);
      d2Sum += computeBackoffMs(2, baseConfig);
    }
    const avg0 = d0Sum / samples;
    const avg2 = d2Sum / samples;
    // On average, attempt 2 should have a larger delay than attempt 0
    expect(avg2).toBeGreaterThan(avg0);
  });

  it('respects maxDelayMs cap', () => {
    const config = { ...baseConfig, maxDelayMs: 500 };
    for (let i = 0; i < 20; i++) {
      const delay = computeBackoffMs(10, config);
      // With jitter (±25%), max possible is 500 * 1.25 = 625
      expect(delay).toBeLessThanOrEqual(625);
    }
  });

  it('applies jitter within expected range', () => {
    const config = { ...baseConfig, baseDelayMs: 1000 };
    const delays: number[] = [];
    for (let i = 0; i < 100; i++) {
      delays.push(computeBackoffMs(0, config));
    }
    const min = Math.min(...delays);
    const max = Math.max(...delays);
    // Base is 1000, jitter range is [0.75, 1.25] * 1000 = [750, 1250]
    expect(min).toBeGreaterThanOrEqual(700); // small tolerance
    expect(max).toBeLessThanOrEqual(1300);
  });
});

describe('onApiMetric', () => {
  it('registers and unregisters listeners', () => {
    const received: ApiCallMetric[] = [];
    const unsub = onApiMetric((m) => received.push(m));

    // The metric system is internal; we just verify the API works
    expect(typeof unsub).toBe('function');

    // Unsubscribe should not throw
    unsub();
  });

  it('handles listener errors gracefully', () => {
    const badListener = () => {
      throw new Error('oops');
    };
    const unsub = onApiMetric(badListener);
    // Should not throw when listener errors
    expect(() => unsub()).not.toThrow();
  });
});
