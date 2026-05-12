import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Activity, CheckCircle, Clock, AlertTriangle, RefreshCw, Play } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { getJobStats, getRecentJobs, retryJob, processJobs, type JobStats, type JobExecution } from '@/api/jobs';

const statusVariant = (status: string): 'default' | 'secondary' | 'destructive' | 'outline' => {
  switch (status) {
    case 'completed': return 'default';
    case 'failed': return 'destructive';
    case 'retrying': return 'secondary';
    case 'running': return 'secondary';
    default: return 'outline';
  }
};

export default function JobMonitor() {
  const { toast } = useToast();
  const [stats, setStats] = useState<JobStats | null>(null);
  const [jobs, setJobs] = useState<JobExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [retrying, setRetrying] = useState<number | null>(null);

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [s, j] = await Promise.all([
        getJobStats(),
        getRecentJobs({ status: statusFilter || undefined }),
      ]);
      setStats(s);
      setJobs(j);
    } catch (error: unknown) {
      toast({ title: 'Failed to load job data', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onRetry(id: number) {
    setRetrying(id);
    try {
      await retryJob(id);
      toast({ title: 'Job retried' });
      await refresh();
    } catch (error: unknown) {
      toast({ title: 'Retry failed', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setRetrying(null);
    }
  }

  async function onProcess() {
    try {
      const result = await processJobs();
      toast({ title: `Processed ${result.processed} jobs` });
      await refresh();
    } catch (error: unknown) {
      toast({ title: 'Process failed', description: getErrorMessage(error, 'Please try again.') });
    }
  }

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Job Monitor</h1>
            <p className="page-subtitle">
              Track background job executions, retries, and failures
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCw className="w-4 h-4" />
              Refresh
            </Button>
            <Button variant="financial" size="sm" onClick={onProcess}>
              <Play className="w-4 h-4" />
              Process Pending
            </Button>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-5 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Pending</FinancialCardTitle>
              <Clock className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground">{stats?.counts.pending ?? 0}</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Running</FinancialCardTitle>
              <Activity className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground">{stats?.counts.running ?? 0}</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Completed</FinancialCardTitle>
              <CheckCircle className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground">{stats?.counts.completed ?? 0}</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={(stats?.counts.failed ?? 0) > 0 ? "destructive" : "financial"}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">Failed</FinancialCardTitle>
              <AlertTriangle className="w-5 h-5" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">{stats?.counts.failed ?? 0}</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Success Rate</FinancialCardTitle>
              <CheckCircle className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground">{stats?.success_rate ?? 0}%</div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2 mb-4">
        {['', 'pending', 'running', 'completed', 'failed', 'retrying'].map((s) => (
          <Button
            key={s}
            variant={statusFilter === s ? 'financial' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(s)}
          >
            {s || 'All'}
          </Button>
        ))}
      </div>

      {/* Recent Jobs Table */}
      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <FinancialCardTitle className="section-title">Recent Jobs</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          {loading ? (
            <div>Loading...</div>
          ) : jobs.length === 0 ? (
            <div className="text-sm text-muted-foreground">No jobs found.</div>
          ) : (
            <div className="space-y-2">
              {jobs.map((job) => (
                <div key={job.id} className="interactive-row flex items-center justify-between border-b py-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{job.job_type}</span>
                      <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      Attempts: {job.attempts}/{job.max_attempts}
                      {job.created_at && ` | Created: ${new Date(job.created_at).toLocaleString()}`}
                      {job.completed_at && ` | Completed: ${new Date(job.completed_at).toLocaleString()}`}
                      {job.next_retry_at && ` | Next retry: ${new Date(job.next_retry_at).toLocaleString()}`}
                    </div>
                    {job.last_error && (
                      <div className="text-xs text-destructive mt-1">
                        Error: {job.last_error}
                      </div>
                    )}
                  </div>
                  {job.status === 'failed' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onRetry(job.id)}
                      disabled={retrying === job.id}
                    >
                      <RefreshCw className={`w-4 h-4 ${retrying === job.id ? 'animate-spin' : ''}`} />
                      Retry
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}
