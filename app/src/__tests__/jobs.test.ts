import { computeJobSummary, type Job, type JobStatus } from '../api/jobs';

describe('computeJobSummary', () => {
  it('returns zeros for empty array', () => {
    const summary = computeJobSummary([]);
    expect(summary).toEqual({
      pending: 0,
      processing: 0,
      sent: 0,
      failed: 0,
      retrying: 0,
      total: 0,
    });
  });

  it('counts jobs by status', () => {
    const jobs: Job[] = [
      { id: '1', type: 'reminder', referenceId: 1, status: 'pending', attempts: 0, maxAttempts: 3, createdAt: '', updatedAt: '' },
      { id: '2', type: 'reminder', referenceId: 2, status: 'sent', attempts: 1, maxAttempts: 3, createdAt: '', updatedAt: '' },
      { id: '3', type: 'reminder', referenceId: 3, status: 'failed', attempts: 3, maxAttempts: 3, createdAt: '', updatedAt: '' },
      { id: '4', type: 'reminder', referenceId: 4, status: 'failed', attempts: 3, maxAttempts: 3, createdAt: '', updatedAt: '' },
      { id: '5', type: 'reminder', referenceId: 5, status: 'retrying', attempts: 2, maxAttempts: 3, createdAt: '', updatedAt: '' },
    ];

    const summary = computeJobSummary(jobs);
    expect(summary).toEqual({
      pending: 1,
      processing: 0,
      sent: 1,
      failed: 2,
      retrying: 1,
      total: 5,
    });
  });

  it('handles all status types', () => {
    const statuses: JobStatus[] = ['pending', 'processing', 'sent', 'failed', 'retrying'];
    const jobs: Job[] = statuses.map((status, i) => ({
      id: String(i),
      type: 'reminder' as const,
      referenceId: i,
      status,
      attempts: 0,
      maxAttempts: 3,
      createdAt: '',
      updatedAt: '',
    }));

    const summary = computeJobSummary(jobs);
    for (const s of statuses) {
      expect(summary[s]).toBe(1);
    }
    expect(summary.total).toBe(5);
  });
});
