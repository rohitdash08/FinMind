import * as monitor from '../lib/request-monitor';

beforeEach(() => {
  monitor.clearCompleted();
});

describe('request-monitor', () => {
  it('tracks request lifecycle', () => {
    const id = monitor.beginRequest('/dashboard', 'GET', 3);
    expect(id).toMatch(/^req-/);

    const snap = monitor.getSnapshot();
    expect(snap).toHaveLength(1);
    expect(snap[0]).toMatchObject({
      path: '/dashboard',
      method: 'GET',
      attempt: 0,
      maxAttempts: 3,
      status: 'pending',
    });
  });

  it('marks retry updates attempt + error', () => {
    const id = monitor.beginRequest('/expenses', 'POST', 3);
    monitor.markRetry(id, 1, 'HTTP 500');

    const entry = monitor.getSnapshot().find((r) => r.id === id)!;
    expect(entry.status).toBe('retrying');
    expect(entry.attempt).toBe(1);
    expect(entry.lastError).toBe('HTTP 500');
  });

  it('marks success then cleans up', () => {
    jest.useFakeTimers();
    const id = monitor.beginRequest('/x', 'GET', 1);
    monitor.markSuccess(id);

    const entry = monitor.getSnapshot().find((r) => r.id === id);
    expect(entry?.status).toBe('succeeded');

    // After 2s it should auto-clean
    jest.advanceTimersByTime(2_100);
    expect(monitor.getSnapshot()).toHaveLength(0);
    jest.useRealTimers();
  });

  it('marks failed', () => {
    const id = monitor.beginRequest('/x', 'DELETE', 3);
    monitor.markFailed(id, 'HTTP 503');

    const entry = monitor.getSnapshot().find((r) => r.id === id);
    expect(entry?.status).toBe('failed');
    expect(entry?.lastError).toBe('HTTP 503');
  });

  it('counts in-flight correctly', () => {
    const a = monitor.beginRequest('/a', 'GET', 3);
    const b = monitor.beginRequest('/b', 'GET', 3);
    monitor.markRetry(a, 1, 'err');
    monitor.markSuccess(b);

    expect(monitor.inFlightCount()).toBe(1); // only 'a' is retrying
  });

  it('counts failed correctly', () => {
    const a = monitor.beginRequest('/a', 'GET', 3);
    const b = monitor.beginRequest('/b', 'GET', 3);
    monitor.markFailed(a, 'err');
    monitor.markFailed(b, 'err');

    expect(monitor.failedCount()).toBe(2);
  });

  it('clearCompleted removes succeeded + failed', () => {
    const a = monitor.beginRequest('/a', 'GET', 3);
    const b = monitor.beginRequest('/b', 'GET', 3);
    const c = monitor.beginRequest('/c', 'GET', 3);
    monitor.markSuccess(a);
    monitor.markFailed(b, 'x');
    // c stays pending

    monitor.clearCompleted();
    const snap = monitor.getSnapshot();
    expect(snap).toHaveLength(1);
    expect(snap[0].id).toBe(c);
  });

  it('notifies subscribers', () => {
    const listener = jest.fn();
    const unsub = monitor.subscribe(listener);

    monitor.beginRequest('/x', 'GET', 1);
    expect(listener).toHaveBeenCalledTimes(1);

    unsub();
    monitor.beginRequest('/y', 'GET', 1);
    // listener should NOT fire after unsubscribe
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
