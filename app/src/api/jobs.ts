import { api } from './client';

/** Status of a background job. */
export type JobStatus = 'pending' | 'processing' | 'sent' | 'failed' | 'retrying';

/** A tracked background job (e.g. reminder dispatch). */
export interface Job {
  id: string;
  type: 'reminder' | 'bill_schedule' | 'autopay_report';
  referenceId: number;
  status: JobStatus;
  attempts: number;
  maxAttempts: number;
  lastError?: string;
  createdAt: string;
  updatedAt: string;
  nextRetryAt?: string;
}

/** Summary counts for the job monitor dashboard. */
export interface JobSummary {
  pending: number;
  processing: number;
  sent: number;
  failed: number;
  retrying: number;
  total: number;
}

/** Fetch recent job statuses from the reminders endpoint. */
export async function listJobs(params?: {
  status?: JobStatus;
  limit?: number;
}): Promise<Job[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set('status', params.status);
  if (params?.limit) query.set('limit', String(params.limit));
  const qs = query.toString();
  return api<Job[]>(`/reminders/jobs${qs ? `?${qs}` : ''}`);
}

/** Retry a failed job by its ID. */
export async function retryJob(jobId: string): Promise<Job> {
  return api<Job>(`/reminders/jobs/${jobId}/retry`, { method: 'POST' });
}

/** Compute a summary from a list of jobs (client-side). */
export function computeJobSummary(jobs: Job[]): JobSummary {
  const summary: JobSummary = {
    pending: 0,
    processing: 0,
    sent: 0,
    failed: 0,
    retrying: 0,
    total: jobs.length,
  };
  for (const job of jobs) {
    if (job.status in summary) {
      summary[job.status as keyof Omit<JobSummary, 'total'>]++;
    }
  }
  return summary;
}
