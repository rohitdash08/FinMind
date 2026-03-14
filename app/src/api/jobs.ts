import { api } from './client';

export type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'DEAD';
export type JobType = 'DATA_SYNC' | 'REPORT_GENERATION' | 'EMAIL_NOTIFICATION';

export type Job = {
  id: number;
  user_id: number;
  name: string;
  job_type: JobType;
  status: JobStatus;
  attempts: number;
  max_retries: number;
  last_error: string | null;
  payload: string | null;
  result: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  next_retry_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type JobListResponse = {
  jobs: Job[];
  total: number;
  page: number;
  per_page: number;
};

export type JobStats = {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  dead: number;
  total: number;
};

export type JobCreate = {
  name: string;
  job_type: JobType;
  payload?: Record<string, unknown>;
  max_retries?: number;
  scheduled_at?: string;
};

export async function listJobs(params?: {
  status?: JobStatus;
  job_type?: JobType;
  page?: number;
  per_page?: number;
}): Promise<JobListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  if (params?.job_type) searchParams.set('job_type', params.job_type);
  if (params?.page) searchParams.set('page', String(params.page));
  if (params?.per_page) searchParams.set('per_page', String(params.per_page));
  const qs = searchParams.toString();
  return api<JobListResponse>(`/jobs${qs ? `?${qs}` : ''}`);
}

export async function createJob(payload: JobCreate): Promise<Job> {
  return api<Job>('/jobs', { method: 'POST', body: payload });
}

export async function getJob(id: number): Promise<Job> {
  return api<Job>(`/jobs/${id}`);
}

export async function retryJob(id: number): Promise<Job> {
  return api<Job>(`/jobs/${id}/retry`, { method: 'POST' });
}

export async function getJobStats(): Promise<JobStats> {
  return api<JobStats>('/jobs/stats');
}

export async function getDeadLetterQueue(): Promise<Job[]> {
  return api<Job[]>('/jobs/dead-letter');
}
