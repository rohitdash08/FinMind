import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import {
  getJobStatus,
  getFailedJobs,
  retryJob,
  clearDeadLetter,
  type JobStatus,
  type FailedJob,
} from '@/api/jobs';

const AUTO_REFRESH_MS = 30_000;

function StatCard({ title, value, variant }: { title: string; value: string | number; variant?: string }) {
  const colorClass =
    variant === 'success'
      ? 'text-green-600 dark:text-green-400'
      : variant === 'danger'
        ? 'text-red-600 dark:text-red-400'
        : variant === 'warning'
          ? 'text-yellow-600 dark:text-yellow-400'
          : 'text-foreground';

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className={`text-3xl ${colorClass}`}>{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

export function JobMonitor() {
  const { toast } = useToast();
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [failedJobs, setFailedJobs] = useState<FailedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [statusData, failedData] = await Promise.all([
        getJobStatus(),
        getFailedJobs(),
      ]);
      setStatus(statusData);
      setFailedJobs(failedData.jobs);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load job data';
      toast({ title: 'Error loading job data', description: msg });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => void fetchData(), AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  async function handleRetry(jobId: string) {
    setActionLoading(jobId);
    try {
      await retryJob(jobId);
      toast({ title: 'Job re-enqueued', description: `Job ${jobId.slice(0, 8)}… queued for retry.` });
      void fetchData();
    } catch (err) {
      toast({ title: 'Retry failed', description: err instanceof Error ? err.message : 'Please try again.' });
    } finally {
      setActionLoading(null);
    }
  }

  async function handleClearDLQ(jobId: string) {
    setActionLoading(jobId);
    try {
      await clearDeadLetter(jobId);
      toast({ title: 'Entry cleared', description: `Dead-letter entry ${jobId.slice(0, 8)}… removed.` });
      void fetchData();
    } catch (err) {
      toast({ title: 'Clear failed', description: err instanceof Error ? err.message : 'Please try again.' });
    } finally {
      setActionLoading(null);
    }
  }

  if (loading) {
    return (
      <div className="page-wrap space-y-6">
        <div className="page-header">
          <h2 className="page-title text-2xl md:text-3xl">Job Monitor</h2>
          <p className="page-subtitle">Loading…</p>
        </div>
      </div>
    );
  }

  const deadJobs = failedJobs.filter((j) => j.state === 'DEAD');
  const retryingJobs = failedJobs.filter((j) => j.state === 'FAILED');

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="page-title text-2xl md:text-3xl">Job Monitor</h2>
            <p className="page-subtitle">
              Background job queue health & management. Auto-refreshes every 30s.
            </p>
          </div>
          <Button variant="outline" onClick={() => void fetchData()}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Alerts */}
      {status?.alerts && status.alerts.length > 0 && (
        <div className="space-y-2">
          {status.alerts.map((alert, i) => (
            <div
              key={i}
              className={`rounded-lg border p-4 ${
                alert.level === 'critical'
                  ? 'border-red-500 bg-red-50 dark:bg-red-950/20'
                  : 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950/20'
              }`}
            >
              <div className="flex items-center gap-2">
                <Badge variant={alert.level === 'critical' ? 'destructive' : 'secondary'}>
                  {alert.level}
                </Badge>
                <span className="text-sm font-medium">{alert.message}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="Pending" value={status?.queue_depth ?? 0} />
        <StatCard title="Active" value={status?.active_workers ?? 0} variant="warning" />
        <StatCard title="Completed" value={status?.completed ?? 0} variant="success" />
        <StatCard title="Dead Letter" value={status?.dlq_size ?? 0} variant={status?.dlq_size ? 'danger' : undefined} />
      </div>

      {/* Metrics Row */}
      {status?.metrics && (
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard title="Total Enqueued" value={status.metrics.enqueued} />
          <StatCard
            title="Success Rate"
            value={`${(status.metrics.success_rate * 100).toFixed(1)}%`}
            variant={status.metrics.success_rate >= 0.9 ? 'success' : 'danger'}
          />
          <StatCard title="Total Retries" value={status.metrics.retries} />
          <StatCard
            title="Avg Duration"
            value={`${status.metrics.avg_duration_seconds.toFixed(2)}s`}
          />
        </div>
      )}

      {/* Failed Jobs (retrying) */}
      {retryingJobs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Retrying Jobs</CardTitle>
            <CardDescription>
              Jobs that failed but have remaining retry attempts.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {retryingJobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-start justify-between rounded-md border p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm">{job.id.slice(0, 12)}…</span>
                      <Badge variant="secondary">{job.job_type}</Badge>
                      <Badge variant="outline">
                        attempt {job.attempts}/{job.max_retries}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{job.error}</p>
                    <p className="text-xs text-muted-foreground">
                      Created: {new Date(job.created_at * 1000).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Dead Letter Queue */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Dead Letter Queue</CardTitle>
          <CardDescription>
            Permanently failed jobs that exhausted all retry attempts.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {deadJobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No dead-letter jobs. All systems healthy.
            </p>
          ) : (
            <div className="space-y-3">
              {deadJobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-start justify-between rounded-md border p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm">{job.id.slice(0, 12)}…</span>
                      <Badge variant="destructive">{job.state}</Badge>
                      <Badge variant="secondary">{job.job_type}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{job.error}</p>
                    <p className="text-xs text-muted-foreground">
                      Attempts: {job.attempts} | Created:{' '}
                      {new Date(job.created_at * 1000).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={actionLoading === job.id}
                      onClick={() => handleRetry(job.id)}
                    >
                      Retry
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={actionLoading === job.id}
                      onClick={() => handleClearDLQ(job.id)}
                    >
                      Clear
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default JobMonitor;
