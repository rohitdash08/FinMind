import { api } from './client';

export interface JobExecution {
  id: number;
  job_id: string;
  job_name: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'RETRYING' | 'DEAD';
  attempt: number;
  max_retries: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  next_retry_at: string | null;
  duration_ms: number | null;
  created_at: string | null;
}

export interface JobStats {
  PENDING: number;
  RUNNING: number;
  SUCCESS: number;
  FAILED: number;
  RETRYING: number;
  DEAD: number;
  total: number;
}

export function listJobs(params?: {
  limit?: number;
  status?: string;
  job_name?: string;
}): Promise<JobExecution[]> {
  const query = new URLSearchParams();
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.status) query.set('status', params.status);
  if (params?.job_name) query.set('job_name', params.job_name);
  const qs = query.toString();
  return api<JobExecution[]>(`/jobs/${qs ? `?${qs}` : ''}`);
}

export function getJobStats(): Promise<JobStats> {
  return api<JobStats>('/jobs/stats');
}

export function getJobDetail(jobId: string): Promise<JobExecution> {
  return api<JobExecution>(`/jobs/${jobId}`);
}

export function retryJob(executionId: number): Promise<JobExecution> {
  return api<JobExecution>(`/jobs/retry/${executionId}`, { method: 'POST' });
}
