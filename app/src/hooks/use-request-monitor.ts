import { useSyncExternalStore, useCallback } from 'react';
import * as monitor from '../lib/request-monitor';
import type { RequestEntry } from '../lib/request-monitor';

/**
 * React hook that subscribes to the global request monitor.
 *
 * Returns:
 *  – `requests` – live list of tracked requests
 *  – `inFlight` – count of pending / retrying requests
 *  – `failed`   – count of failed requests
 *  – `clear()`  – remove completed entries
 *
 * ```tsx
 * const { inFlight, failed, requests, clear } = useRequestMonitor();
 * if (failed > 0) toast.error(`${failed} request(s) failed`);
 * ```
 */
export function useRequestMonitor() {
  const requests = useSyncExternalStore(
    monitor.subscribe,
    monitor.getSnapshot,
    monitor.getSnapshot, // server snapshot (same impl)
  );

  const inFlight = requests.filter(
    (r) => r.status === 'pending' || r.status === 'retrying',
  ).length;

  const failed = requests.filter((r) => r.status === 'failed').length;

  const clear = useCallback(() => monitor.clearCompleted(), []);

  return { requests, inFlight, failed, clear } as const;
}

/**
 * Lightweight hook that returns only the in-flight count.
 * Useful for global loading indicators / badges.
 */
export function useInFlightCount(): number {
  const requests = useSyncExternalStore(
    monitor.subscribe,
    monitor.getSnapshot,
    monitor.getSnapshot,
  );
  return requests.filter(
    (r) => r.status === 'pending' || r.status === 'retrying',
  ).length;
}

export type { RequestEntry };
