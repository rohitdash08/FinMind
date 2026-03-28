import { useState, useCallback, useRef, useEffect } from 'react';

export type JobStatus = 'idle' | 'running' | 'success' | 'failed' | 'retrying';

export interface JobState<T = unknown> {
  id: string;
  status: JobStatus;
  result: T | null;
  error: string | null;
  attempts: number;
  maxAttempts: number;
  nextRetryIn: number | null; // ms
}

export interface UseJobQueueOptions {
  maxAttempts?: number;
  baseDelay?: number; // ms
  maxDelay?: number; // ms
  backoffMultiplier?: number;
  jitter?: boolean;
  onStatusChange?: (status: JobStatus, attempt: number) => void;
  onSuccess?: (result: unknown) => void;
  onFailure?: (error: string, attempts: number) => void;
}

const DEFAULT_OPTIONS: Required<UseJobQueueOptions> = {
  maxAttempts: 3,
  baseDelay: 1000,
  maxDelay: 30000,
  backoffMultiplier: 2,
  jitter: true,
  onStatusChange: () => {},
  onSuccess: () => {},
  onFailure: () => {},
};

function calculateDelay(attempt: number, options: Required<UseJobQueueOptions>): number {
  const exponential = options.baseDelay * Math.pow(options.backoffMultiplier, attempt - 1);
  const capped = Math.min(exponential, options.maxDelay);
  if (options.jitter) {
    return capped * (0.5 + Math.random() * 0.5);
  }
  return capped;
}

export function useJobQueue<T = unknown>(options: UseJobQueueOptions = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const [jobs, setJobs] = useState<Map<string, JobState<T>>>(new Map());
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const cancelledRef = useRef<Set<string>>(new Set());

  // Cleanup on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const updateJob = useCallback((id: string, update: Partial<JobState<T>>) => {
    setJobs((prev) => {
      const next = new Map(prev);
      const existing = next.get(id);
      if (existing) {
        next.set(id, { ...existing, ...update });
      }
      return next;
    });
  }, []);

  const executeWithRetry = useCallback(
    async (id: string, task: () => Promise<T>, attempt: number = 1) => {
      if (cancelledRef.current.has(id)) {
        updateJob(id, { status: 'failed', error: 'Cancelled' });
        return;
      }

      updateJob(id, { status: attempt > 1 ? 'retrying' : 'running', attempts: attempt, error: null });
      opts.onStatusChange(attempt > 1 ? 'retrying' : 'running', attempt);

      try {
        const result = await task();
        updateJob(id, { status: 'success', result });
        opts.onStatusChange('success', attempt);
        opts.onSuccess(result);
      } catch (err: unknown) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error';

        if (attempt >= opts.maxAttempts || cancelledRef.current.has(id)) {
          updateJob(id, { status: 'failed', error: errorMessage });
          opts.onStatusChange('failed', attempt);
          opts.onFailure(errorMessage, attempt);
          return;
        }

        const delay = calculateDelay(attempt, opts);
        updateJob(id, {
          status: 'retrying',
          error: errorMessage,
          nextRetryIn: delay,
        });
        opts.onStatusChange('retrying', attempt);

        const timer = setTimeout(() => {
          timersRef.current.delete(id);
          executeWithRetry(id, task, attempt + 1);
        }, delay);

        timersRef.current.set(id, timer);
      }
    },
    [opts, updateJob]
  );

  const enqueue = useCallback(
    (id: string, task: () => Promise<T>) => {
      cancelledRef.current.delete(id);
      const initialState: JobState<T> = {
        id,
        status: 'idle',
        result: null,
        error: null,
        attempts: 0,
        maxAttempts: opts.maxAttempts,
        nextRetryIn: null,
      };
      setJobs((prev) => {
        const next = new Map(prev);
        next.set(id, initialState);
        return next;
      });
      executeWithRetry(id, task);
    },
    [executeWithRetry, opts.maxAttempts]
  );

  const cancel = useCallback((id: string) => {
    cancelledRef.current.add(id);
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const retry = useCallback(
    (id: string, task: () => Promise<T>) => {
      cancelledRef.current.delete(id);
      const existing = jobs.get(id);
      if (existing) {
        updateJob(id, { attempts: 0, error: null, result: null });
      }
      executeWithRetry(id, task);
    },
    [jobs, executeWithRetry, updateJob]
  );

  const getJob = useCallback((id: string) => jobs.get(id), [jobs]);

  return {
    jobs: Array.from(jobs.values()),
    enqueue,
    cancel,
    retry,
    getJob,
  };
}
