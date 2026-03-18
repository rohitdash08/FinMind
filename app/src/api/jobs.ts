import { api } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type JobMetrics = {
  enqueued: number;
  succeeded: number;
  dead: number;
  retries: number;
  manual_retries: number;
  success_rate: number;
  failure_rate: number;
  avg_duration_seconds: number;
};

export type JobAlert = {
  level: 'critical' | 'warning';
  type: string;
  message: string;
  value: number;
  threshold: number;
};

export type JobStatus = {
  queue_depth: number;
  active_workers: number;
  completed: number;
  dlq_size: number;
  metrics: JobMetrics;
  alerts: JobAlert[];
  timestamp: number;
};

export type FailedJob = {
  id: string;
  job_type: string;
  payload: Record<string, unknown>;
  state: 'FAILED' | 'DEAD';
  attempts: number;
  max_retries: number;
  error: string;
  created_at: number;
  updated_at: number;
};

export type FailedJobsResponse = {
  jobs: FailedJob[];
  count: number;
};

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/** Fetch dashboard status: queue depth, metrics, alerts. */
export async function getJobStatus(): Promise<JobStatus> {
  return api<JobStatus>('/jobs/status');
}

/** List failed and dead-letter jobs. */
export async function getFailedJobs(limit = 50): Promise<FailedJobsResponse> {
  return api<FailedJobsResponse>(`/jobs/failed?limit=${limit}`);
}

/** Manually retry a failed or dead-letter job. */
export async function retryJob(jobId: string): Promise<{ message: string; job_id: string }> {
  return api<{ message: string; job_id: string }>(`/jobs/retry/${jobId}`, {
    method: 'POST',
  });
}

/** Clear a dead-letter queue entry. */
export async function clearDeadLetter(jobId: string): Promise<{ message: string; job_id: string }> {
  return api<{ message: string; job_id: string }>(`/jobs/dead-letter/${jobId}`, {
    method: 'DELETE',
  });
}
