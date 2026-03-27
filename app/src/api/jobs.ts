import { api } from './client';

export type JobStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'RETRYING' | 'DEAD';

export type Job = {
  id: number;
  name: string;
  status: JobStatus;
  attempts: number;
  max_retries: number;
  last_error: string | null;
  result: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type JobStats = {
  total: number;
  by_status: Record<string, number>;
  success_rate: number;
};

export async function getJobStats(): Promise<JobStats> {
  return api<JobStats>('/jobs/stats');
}

export async function getRecentJobs(limit = 20): Promise<Job[]> {
  return api<Job[]>(`/jobs/recent?limit=${limit}`);
}

export async function getDeadLetterJobs(limit = 50): Promise<Job[]> {
  return api<Job[]>(`/jobs/dead-letter?limit=${limit}`);
}

export async function getJob(id: number): Promise<Job> {
  return api<Job>(`/jobs/${id}`);
}

export async function retryJob(id: number): Promise<Job> {
  return api<Job>(`/jobs/${id}/retry`, { method: 'POST' });
}
