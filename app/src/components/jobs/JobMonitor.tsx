import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import {
  listJobs,
  retryJob,
  computeJobSummary,
  type Job,
  type JobSummary,
  type JobStatus,
} from '@/api/jobs';
import { onApiMetric, type ApiCallMetric } from '@/api/client';

const STATUS_COLORS: Record<JobStatus, string> = {
  pending: 'bg-yellow-500/10 text-yellow-700 border-yellow-500/30',
  processing: 'bg-blue-500/10 text-blue-700 border-blue-500/30',
  sent: 'bg-green-500/10 text-green-700 border-green-500/30',
  failed: 'bg-red-500/10 text-red-700 border-red-500/30',
  retrying: 'bg-orange-500/10 text-orange-700 border-orange-500/30',
};

/** Live API call metric entry for the metrics panel. */
interface MetricEntry extends ApiCallMetric {
  timestamp: number;
}

export function JobMonitor() {
  const { toast } = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [summary, setSummary] = useState<JobSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<JobStatus | 'all'>('all');
  const [metrics, setMetrics] = useState<MetricEntry[]>([]);
  const [showMetrics, setShowMetrics] = useState(false);

  // Subscribe to API call metrics for real-time monitoring
  useEffect(() => {
    const unsub = onApiMetric((metric) => {
      setMetrics((prev) => {
        const next = [{ ...metric, timestamp: Date.now() }, ...prev];
        return next.slice(0, 50); // keep last 50
      });
    });
    return unsub;
  }, []);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const statusParam = filter === 'all' ? undefined : filter;
      const data = await listJobs({ status: statusParam, limit: 100 });
      setJobs(data);
      setSummary(computeJobSummary(data));
    } catch {
      toast({ title: 'Failed to load jobs', description: 'Please try again.' });
    } finally {
      setLoading(false);
    }
  }, [filter, toast]);

  useEffect(() => {
    void loadJobs();
    // Auto-refresh every 30 seconds
    const interval = setInterval(() => void loadJobs(), 30_000);
    return () => clearInterval(interval);
  }, [loadJobs]);

  async function handleRetry(jobId: string) {
    try {
      await retryJob(jobId);
      toast({ title: 'Retry queued', description: `Job ${jobId} will be retried.` });
      await loadJobs();
    } catch {
      toast({ title: 'Failed to retry job', description: 'Please try again.' });
    }
  }

  const filteredJobs = filter === 'all' ? jobs : jobs.filter((j) => j.status === filter);

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {(Object.keys(STATUS_COLORS) as JobStatus[]).map((status) => (
            <Card
              key={status}
              className={`p-3 cursor-pointer transition-opacity ${filter === status ? 'opacity-100 ring-2 ring-primary' : 'opacity-70 hover:opacity-100'}`}
              onClick={() => setFilter(filter === status ? 'all' : status)}
            >
              <div className="text-xs text-muted-foreground capitalize">{status}</div>
              <div className="text-2xl font-bold">{summary[status]}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void loadJobs()} disabled={loading}>
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowMetrics(!showMetrics)}
          >
            {showMetrics ? 'Hide' : 'Show'} API Metrics
          </Button>
        </div>
        <div className="text-xs text-muted-foreground">
          Auto-refreshes every 30s • {summary?.total ?? 0} total jobs
        </div>
      </div>

      {/* API Metrics panel */}
      {showMetrics && (
        <Card className="p-3 space-y-2">
          <h4 className="text-sm font-semibold">Live API Metrics</h4>
          {metrics.length === 0 ? (
            <div className="text-xs text-muted-foreground">No API calls recorded yet.</div>
          ) : (
            <div className="max-h-48 overflow-y-auto space-y-1">
              {metrics.map((m, i) => (
                <div
                  key={`${m.timestamp}-${i}`}
                  className={`text-xs font-mono flex items-center gap-2 ${m.retried ? 'text-orange-600' : m.status >= 400 ? 'text-red-600' : 'text-green-600'}`}
                >
                  <span className="w-8">{m.method}</span>
                  <span className="flex-1 truncate">{m.path}</span>
                  <span className="w-10 text-right">{m.status}</span>
                  <span className="w-16 text-right">{m.durationMs}ms</span>
                  <span className="w-12 text-right">#{m.attempt}</span>
                  {m.retried && <Badge variant="outline" className="text-[10px] px-1">retry</Badge>}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Job list */}
      <Card className="p-4">
        {loading && jobs.length === 0 ? (
          <div className="text-sm text-muted-foreground">Loading jobs…</div>
        ) : filteredJobs.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No {filter === 'all' ? '' : filter} jobs found.
          </div>
        ) : (
          <div className="space-y-2">
            {filteredJobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between border-b py-2 last:border-0"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge className={`border ${STATUS_COLORS[job.status]}`}>{job.status}</Badge>
                    <span className="font-medium truncate">{job.type}</span>
                    <span className="text-xs text-muted-foreground">
                      ref #{job.referenceId}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Attempts: {job.attempts}/{job.maxAttempts}
                    {job.lastError && (
                      <span className="text-red-600 ml-2">Error: {job.lastError}</span>
                    )}
                    {job.nextRetryAt && (
                      <span className="ml-2">
                        Next retry: {new Date(job.nextRetryAt).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
                {job.status === 'failed' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRetry(job.id)}
                  >
                    Retry
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default JobMonitor;
