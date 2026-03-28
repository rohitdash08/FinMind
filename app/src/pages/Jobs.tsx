import { useState, useEffect, useMemo } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  AlertTriangle,
  Play,
  Pause,
  Trash2,
  Activity,
  Zap,
  BarChart3,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import type { BackgroundJob, JobStatus, JobStats } from '@/api/jobs';

// --- Mock Data --------------------------------------------------------------

const JOB_TYPES = ['sync_accounts', 'generate_report', 'send_reminder', 'import_csv', 'budget_alert'];

function generateMockJobs(): BackgroundJob[] {
  const statuses: JobStatus[] = ['pending', 'running', 'success', 'failed', 'retrying', 'cancelled'];
  const jobs: BackgroundJob[] = [];
  const now = Date.now();

  for (let i = 0; i < 20; i++) {
    const status = statuses[Math.floor(Math.random() * statuses.length)];
    const createdAt = new Date(now - Math.random() * 86400000 * 7).toISOString();
    const attempts = status === 'success' ? 1 : status === 'retrying' ? Math.floor(1 + Math.random() * 3) : 1;

    jobs.push({
      id: `job-${i + 1}`,
      type: JOB_TYPES[Math.floor(Math.random() * JOB_TYPES.length)],
      status,
      payload: {},
      attempts,
      maxAttempts: 3,
      error: status === 'failed' ? 'Connection timeout after 30s' : undefined,
      nextRetryAt: status === 'retrying' ? new Date(now + Math.random() * 60000).toISOString() : undefined,
      createdAt,
      startedAt: status !== 'pending' ? createdAt : undefined,
      completedAt: ['success', 'failed', 'cancelled'].includes(status) ? new Date(now - Math.random() * 3600000).toISOString() : undefined,
      updatedAt: createdAt,
    });
  }

  return jobs.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

function generateMockStats(jobs: BackgroundJob[]): JobStats {
  const success = jobs.filter((j) => j.status === 'success').length;
  const total = jobs.length;
  return {
    total,
    pending: jobs.filter((j) => j.status === 'pending').length,
    running: jobs.filter((j) => j.status === 'running').length,
    success,
    failed: jobs.filter((j) => j.status === 'failed').length,
    retrying: jobs.filter((j) => j.status === 'retrying').length,
    avgDurationMs: 2450,
    successRate: total > 0 ? Math.round((success / total) * 100) : 0,
  };
}

// --- Helpers ----------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function StatusIcon({ status }: { status: JobStatus }) {
  switch (status) {
    case 'success':
      return <CheckCircle2 className="h-4 w-4 text-success" />;
    case 'failed':
      return <XCircle className="h-4 w-4 text-destructive" />;
    case 'running':
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    case 'retrying':
      return <RefreshCw className="h-4 w-4 text-warning animate-spin" />;
    case 'pending':
      return <Clock className="h-4 w-4 text-muted-foreground" />;
    case 'cancelled':
      return <Pause className="h-4 w-4 text-muted-foreground" />;
  }
}

function StatusBadge({ status }: { status: JobStatus }) {
  const variants: Record<JobStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    success: 'default',
    running: 'secondary',
    retrying: 'outline',
    pending: 'outline',
    failed: 'destructive',
    cancelled: 'outline',
  };
  return (
    <Badge variant={variants[status]} className="gap-1">
      <StatusIcon status={status} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}

// --- Component --------------------------------------------------------------

export function Jobs() {
  const [jobs, setJobs] = useState<BackgroundJob[]>(generateMockJobs);
  const [filter, setFilter] = useState<JobStatus | 'all'>('all');
  const { toast } = useToast();

  const filteredJobs = useMemo(() => {
    if (filter === 'all') return jobs;
    return jobs.filter((j) => j.status === filter);
  }, [jobs, filter]);

  const stats = useMemo(() => generateMockStats(jobs), [jobs]);

  const handleRetry = (job: BackgroundJob) => {
    setJobs((prev) =>
      prev.map((j) =>
        j.id === job.id ? { ...j, status: 'running' as JobStatus, attempts: 0, error: undefined } : j
      )
    );
    toast({ title: 'Job Retrying', description: `"${job.type}" has been queued for retry.` });

    // Simulate success after 2s
    setTimeout(() => {
      setJobs((prev) =>
        prev.map((j) =>
          j.id === job.id ? { ...j, status: 'success' as JobStatus, attempts: 1, completedAt: new Date().toISOString() } : j
        )
      );
      toast({ title: 'Job Succeeded', description: `"${job.type}" completed successfully.` });
    }, 2000);
  };

  const handleCancel = (job: BackgroundJob) => {
    setJobs((prev) =>
      prev.map((j) =>
        j.id === job.id ? { ...j, status: 'cancelled' as JobStatus, completedAt: new Date().toISOString() } : j
      )
    );
    toast({ title: 'Job Cancelled', description: `"${job.type}" has been cancelled.` });
  };

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Job Monitor</h1>
          <p className="text-muted-foreground">Track and manage background job execution.</p>
        </div>
        <Button variant="outline" className="gap-2" onClick={() => setJobs(generateMockJobs())}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4 lg:grid-cols-6">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <Activity className="h-3 w-3" /> Total Jobs
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">{stats.total}</FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Success Rate</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-success">{stats.successRate}%</FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-success" /> Succeeded
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">{stats.success}</FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <XCircle className="h-3 w-3 text-destructive" /> Failed
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-destructive">{stats.failed}</FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <Loader2 className="h-3 w-3" /> Running
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">{stats.running}</FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <Zap className="h-3 w-3" /> Avg Duration
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">{formatDuration(stats.avgDurationMs)}</FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
      </div>

      {/* Filter */}
      <div className="flex gap-2 flex-wrap">
        {(['all', 'pending', 'running', 'success', 'failed', 'retrying', 'cancelled'] as const).map((f) => (
          <Button
            key={f}
            variant={filter === f ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
          </Button>
        ))}
      </div>

      {/* Jobs Table */}
      <FinancialCard>
        <FinancialCardHeader>
          <FinancialCardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Jobs ({filteredJobs.length})
          </FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="space-y-3">
            {filteredJobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <StatusIcon status={job.status} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{job.type}</span>
                      <span className="text-xs text-muted-foreground">{job.id}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>Attempt {job.attempts}/{job.maxAttempts}</span>
                      <span>{formatTime(job.createdAt)}</span>
                      {job.error && (
                        <span className="text-destructive truncate max-w-[200px]">{job.error}</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={job.status} />
                  {job.status === 'failed' && (
                    <Button size="sm" variant="outline" className="gap-1" onClick={() => handleRetry(job)}>
                      <RefreshCw className="h-3 w-3" /> Retry
                    </Button>
                  )}
                  {(job.status === 'running' || job.status === 'pending') && (
                    <Button size="sm" variant="outline" className="gap-1" onClick={() => handleCancel(job)}>
                      <Pause className="h-3 w-3" /> Cancel
                    </Button>
                  )}
                </div>
              </div>
            ))}
            {filteredJobs.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                No jobs matching this filter.
              </div>
            )}
          </div>
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}
