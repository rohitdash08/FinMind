import { apiClient } from './client';

export type JobStatus = 'pending' | 'running' | 'success' | 'failed' | 'retrying' | 'cancelled';

export interface BackgroundJob {
  id: string;
  type: string;
  status: JobStatus;
  payload: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string;
  attempts: number;
  maxAttempts: number;
  nextRetryAt?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  updatedAt: string;
}

export interface JobStats {
  total: number;
  pending: number;
  running: number;
  success: number;
  failed: number;
  retrying: number;
  avgDurationMs: number;
  successRate: number;
}

export interface CreateJobRequest {
  type: string;
  payload: Record<string, unknown>;
  maxAttempts?: number;
}

export const getJobs = async (status?: JobStatus): Promise<BackgroundJob[]> => {
  const params = status ? { status } : {};
  const response = await apiClient.get('/jobs', { params });
  return response.data;
};

export const getJob = async (id: string): Promise<BackgroundJob> => {
  const response = await apiClient.get(`/jobs/${id}`);
  return response.data;
};

export const createJob = async (data: CreateJobRequest): Promise<BackgroundJob> => {
  const response = await apiClient.post('/jobs', data);
  return response.data;
};

export const cancelJob = async (id: string): Promise<BackgroundJob> => {
  const response = await apiClient.post(`/jobs/${id}/cancel`);
  return response.data;
};

export const retryJob = async (id: string): Promise<BackgroundJob> => {
  const response = await apiClient.post(`/jobs/${id}/retry`);
  return response.data;
};

export const getJobStats = async (): Promise<JobStats> => {
  const response = await apiClient.get('/jobs/stats');
  return response.data;
};

export const deleteJob = async (id: string): Promise<void> => {
  await apiClient.delete(`/jobs/${id}`);
};
