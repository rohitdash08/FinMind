import { api } from './client';

export type Job = {
  id: string;
  job_type: string;
  status: 'pending' | 'running' | 'failed' | 'complete';
  retry_count: number;
  next_retry_at: string | null;
  created_at: string;
  completed_at: string | null;
  failures: { timestamp: string; error: string }[];
};

export async function listJobs(): Promise<Job[]> {
  return api<Job[]>('/jobs');
}

export async function createJob(job_type: string): Promise<Job> {
  return api<Job>('/jobs', { method: 'POST', body: { job_type } });
}

export async function getJob(id: string): Promise<Job> {
  return api<Job>(`/jobs/${id}`);
}
