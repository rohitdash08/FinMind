/**
 * In-flight request monitor.
 *
 * Tracks every API call through the client, exposing:
 *  – queue depth
 *  – success / failure counts
 *  – per-request metadata (path, start time, retry count, last error)
 *
 * The monitor is a plain singleton so it works outside React (tests, SSR).
 */

export interface RequestEntry {
  id: string;
  path: string;
  method: string;
  startedAt: number;
  attempt: number;
  maxAttempts: number;
  lastError?: string;
  status: 'pending' | 'retrying' | 'succeeded' | 'failed';
}

export type MonitorListener = (snapshot: RequestEntry[]) => void;

let counter = 0;
const requests = new Map<string, RequestEntry>();
const listeners = new Set<MonitorListener>();

function notify() {
  const snapshot = Array.from(requests.values());
  for (const fn of listeners) fn(snapshot);
}

export function subscribe(listener: MonitorListener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getSnapshot(): RequestEntry[] {
  return Array.from(requests.values());
}

/** Register a new request and return its unique id. */
export function beginRequest(
  path: string,
  method: string,
  maxAttempts: number,
): string {
  const id = `req-${++counter}`;
  requests.set(id, {
    id,
    path,
    method,
    startedAt: Date.now(),
    attempt: 0,
    maxAttempts,
    status: 'pending',
  });
  notify();
  return id;
}

export function markRetry(id: string, attempt: number, error: string) {
  const entry = requests.get(id);
  if (!entry) return;
  entry.attempt = attempt;
  entry.status = 'retrying';
  entry.lastError = error;
  notify();
}

export function markSuccess(id: string) {
  const entry = requests.get(id);
  if (!entry) return;
  entry.status = 'succeeded';
  notify();
  // Auto-clean after 2 s so the UI can show a brief success flash.
  setTimeout(() => { requests.delete(id); notify(); }, 2_000);
}

export function markFailed(id: string, error: string) {
  const entry = requests.get(id);
  if (!entry) return;
  entry.status = 'failed';
  entry.lastError = error;
  notify();
}

/** Remove completed/failed entries (garbage collection). */
export function clearCompleted() {
  for (const [id, entry] of requests) {
    if (entry.status === 'succeeded' || entry.status === 'failed') {
      requests.delete(id);
    }
  }
  notify();
}

/** Total in-flight (pending + retrying) requests. */
export function inFlightCount(): number {
  let n = 0;
  for (const entry of requests.values()) {
    if (entry.status === 'pending' || entry.status === 'retrying') n++;
  }
  return n;
}

/** Count of failed requests still tracked. */
export function failedCount(): number {
  let n = 0;
  for (const entry of requests.values()) {
    if (entry.status === 'failed') n++;
  }
  return n;
}
