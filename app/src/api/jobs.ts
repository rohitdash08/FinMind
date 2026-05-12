import { api } from './client';

export type JobExecution = {
  id: number;
  job_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'retrying';
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  next_retry_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
};

export type JobStats = {
  counts: {
    pending: number;
    running: number;
    completed: number;
    failed: number;
    retrying: number;
  };
  total: number;
  success_rate: number;
  recent_failures: {
    id: number;
    job_type: string;
    last_error: string | null;
    attempts: number;
    created_at: string | null;
  }[];
};

export async function getJobStats(): Promise<JobStats> {
  return api<JobStats>('/jobs/stats');
}

export async function getRecentJobs(params?: {
  status?: string;
  job_type?: string;
  limit?: number;
}): Promise<JobExecution[]> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
    });
  }
  const path = '/jobs/recent' + (qs.toString() ? `?${qs.toString()}` : '');
  return api<JobExecution[]>(path);
}

export async function retryJob(id: number): Promise<{ id: number; status: string; attempts: number; last_error: string | null }> {
  return api(`/jobs/retry/${id}`, { method: 'POST' });
}

export async function processJobs(): Promise<{ processed: number }> {
  return api('/jobs/process', { method: 'POST' });
}
